"""
Connectivity Manager - Gerencia estado de conectividade com a nuvem
"""

import asyncio
import httpx
import logging
from datetime import datetime
from collections import deque
from typing import Literal

from db.repository import QueueRepository

logger = logging.getLogger(__name__)

ConnectivityState = Literal['ONLINE', 'OFFLINE', 'DEGRADED', 'FORCED_OFFLINE', 'UNKNOWN']

class ConnectivityManager:
    """
    Gerencia conectividade com a API de produção
    
    Estados:
    - ONLINE: Internet OK, API acessível
    - OFFLINE: Sem internet ou API inacessível
    - DEGRADED: Internet lenta/instável
    - FORCED_OFFLINE: Modo forçado offline (configuração)
    - UNKNOWN: Estado inicial
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.repository = QueueRepository(config['database']['path'])
        
        # Configurações
        self.healthcheck_url = config['cloud']['healthcheck_url']
        self.healthcheck_interval = config['cloud']['healthcheck_interval']
        self.healthcheck_timeout = config['cloud']['healthcheck_timeout']
        
        # Histerese (evitar alternância rápida)
        self.offline_threshold = config['connectivity']['offline_threshold']
        self.online_threshold = config['connectivity']['online_threshold']
        self.degraded_latency_ms = config['connectivity']['degraded_latency_ms']
        
        # Janela deslizante de resultados (últimos N checks)
        self.recent_checks = deque(maxlen=10)
        
        # Estado atual
        self.current_state: ConnectivityState = 'UNKNOWN'
        
        # Verificar se modo forçado offline
        self.forced_offline = config.get('mode') == 'FORCED_OFFLINE'
        
        logger.info("ConnectivityManager inicializado")
        logger.info(f"Healthcheck URL: {self.healthcheck_url}")
        logger.info(f"Interval: {self.healthcheck_interval}s")
        logger.info(f"Modo forçado offline: {self.forced_offline}")
    
    async def run(self):
        """Loop principal de verificação de conectividade"""
        logger.info("🌐 Connectivity Manager iniciado")
        
        # Se modo forçado offline, setar e não fazer checks
        if self.forced_offline:
            logger.warning("⚠️  Modo FORCED_OFFLINE ativado")
            self._set_state('FORCED_OFFLINE')
            
            # Manter rodando mas sem fazer checks
            try:
                while True:
                    await asyncio.sleep(60)  # Apenas aguardar
            except KeyboardInterrupt:
                logger.info("Parando connectivity manager...")
            return
        
        # Loop normal de verificação
        try:
            while True:
                await self._check_connectivity()
                await asyncio.sleep(self.healthcheck_interval)
        except KeyboardInterrupt:
            logger.info("Parando connectivity manager...")
    
    async def _check_connectivity(self):
        """
        Verifica conectividade com a nuvem
        Faz healthcheck HTTP e mede latência
        """
        try:
            async with httpx.AsyncClient() as client:
                start = datetime.now()
                
                response = await client.get(
                    self.healthcheck_url,
                    timeout=self.healthcheck_timeout
                )
                
                latency_ms = (datetime.now() - start).total_seconds() * 1000
                
                if response.status_code == 200:
                    self.recent_checks.append(('SUCCESS', latency_ms))
                    logger.debug(f"✅ Healthcheck OK - {latency_ms:.0f}ms")
                else:
                    self.recent_checks.append(('FAILED', None))
                    logger.warning(f"⚠️  Healthcheck failed - HTTP {response.status_code}")
        
        except httpx.TimeoutException:
            self.recent_checks.append(('FAILED', None))
            logger.warning(f"⚠️  Healthcheck timeout ({self.healthcheck_timeout}s)")
        
        except httpx.ConnectError as e:
            self.recent_checks.append(('FAILED', None))
            logger.warning(f"⚠️  Healthcheck connection error: {e}")
        
        except Exception as e:
            self.recent_checks.append(('FAILED', None))
            logger.error(f"❌ Healthcheck error: {e}")
        
        # Atualizar estado baseado em histerese
        self._update_state()
    
    def _update_state(self):
        """
        Atualiza estado baseado em histerese
        
        Histerese evita alternância rápida entre estados:
        - Precisa de N falhas consecutivas para marcar OFFLINE
        - Precisa de N sucessos consecutivos para marcar ONLINE
        """
        # Precisa de pelo menos 3 checks para decidir
        if len(self.recent_checks) < 3:
            logger.debug("Aguardando mais checks para decidir estado")
            return
        
        # Pegar últimos 3 checks
        recent_list = list(self.recent_checks)
        last_3 = recent_list[-3:]
        
        # Contar sucessos e falhas
        successes = sum(1 for status, _ in last_3 if status == 'SUCCESS')
        failures = sum(1 for status, _ in last_3 if status == 'FAILED')
        
        # Calcular latência média dos sucessos recentes
        recent_successes = [(status, latency) for status, latency in recent_list if status == 'SUCCESS']
        if recent_successes:
            avg_latency = sum(lat for _, lat in recent_successes) / len(recent_successes)
        else:
            avg_latency = None
        
        # Determinar novo estado
        new_state = self.current_state
        
        # Histerese para OFFLINE
        if failures >= self.offline_threshold:
            new_state = 'OFFLINE'
        
        # Histerese para ONLINE
        elif successes >= self.online_threshold:
            # Verificar se latência está degradada
            if avg_latency and avg_latency > self.degraded_latency_ms:
                new_state = 'DEGRADED'
            else:
                new_state = 'ONLINE'
        
        # Se não atingiu threshold, manter estado atual
        # (isso evita alternância rápida)
        
        # Atualizar se mudou
        if new_state != self.current_state:
            old_state = self.current_state
            self.current_state = new_state
            self._set_state(new_state)
            
            logger.info(f"🔄 Estado mudou: {old_state} → {new_state}")
            
            # Log adicional para transições importantes
            if new_state == 'OFFLINE':
                logger.warning("⚠️  Sistema OFFLINE - processamento local será ativado")
            elif new_state == 'ONLINE' and old_state == 'OFFLINE':
                logger.info("✅ Sistema voltou ONLINE - retomando envio para nuvem")
    
    def _set_state(self, state: ConnectivityState):
        """
        Persiste estado no banco de dados
        
        Args:
            state: Novo estado
        """
        try:
            self.repository.set_system_state('connectivity_state', state)
            logger.debug(f"Estado persistido: {state}")
        except Exception as e:
            logger.error(f"Erro ao persistir estado: {e}")
    
    def get_current_state(self) -> ConnectivityState:
        """
        Retorna estado atual
        
        Returns:
            Estado atual
        """
        return self.current_state
    
    def is_online(self) -> bool:
        """
        Verifica se está online
        
        Returns:
            True se ONLINE ou DEGRADED
        """
        return self.current_state in ('ONLINE', 'DEGRADED')
    
    def is_offline(self) -> bool:
        """
        Verifica se está offline
        
        Returns:
            True se OFFLINE ou FORCED_OFFLINE
        """
        return self.current_state in ('OFFLINE', 'FORCED_OFFLINE')
    
    def get_stats(self) -> dict:
        """
        Retorna estatísticas de conectividade
        
        Returns:
            Dict com estatísticas
        """
        recent_list = list(self.recent_checks)
        
        total_checks = len(recent_list)
        successes = sum(1 for status, _ in recent_list if status == 'SUCCESS')
        failures = sum(1 for status, _ in recent_list if status == 'FAILED')
        
        # Latência média
        success_latencies = [lat for status, lat in recent_list if status == 'SUCCESS' and lat]
        avg_latency = sum(success_latencies) / len(success_latencies) if success_latencies else None
        
        return {
            'current_state': self.current_state,
            'total_checks': total_checks,
            'successes': successes,
            'failures': failures,
            'success_rate': (successes / total_checks * 100) if total_checks > 0 else 0,
            'avg_latency_ms': round(avg_latency, 2) if avg_latency else None,
            'forced_offline': self.forced_offline
        }
