"""Eventos do barramento (arquitetura de microsserviços).

O central é fonte da verdade: publica replicação de dados mestres e consome resultados.
A entrega é garantida pelo padrão outbox (grava na mesma transação, relay publica depois).
Ver pp-app/docs/arquitetura-plataforma.md e contrato-evento-resultado.md.
"""
