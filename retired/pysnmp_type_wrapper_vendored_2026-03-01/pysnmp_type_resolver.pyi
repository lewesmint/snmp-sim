from .interfaces import SnmpTypeFactory, SupportsMibBuilder

class PysnmpTypeResolver:
    def resolve_type_factory(
        self,
        base_type: str,
        mib_builder: SupportsMibBuilder | None,
    ) -> SnmpTypeFactory | None: ...
