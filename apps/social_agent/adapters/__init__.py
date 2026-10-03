from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishResult:
    external_message_id: str


class ChannelAdapter(ABC):
    capabilities: set[str] = set()

    @abstractmethod
    def publish(self, post) -> PublishResult:
        raise NotImplementedError


_ADAPTERS: dict[str, type[ChannelAdapter]] = {}


def register_adapter(platform: str, adapter_cls: type[ChannelAdapter]) -> None:
    _ADAPTERS[platform] = adapter_cls


def get_adapter(platform: str) -> type[ChannelAdapter] | None:
    return _ADAPTERS.get(platform)


def is_platform_supported(platform: str) -> bool:
    return platform in _ADAPTERS
