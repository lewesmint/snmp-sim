from __future__ import annotations

import subprocess
import time
from collections.abc import Iterable

from snmp_traps.trap_receiver import TrapReceiver


class DebugTrapReceiver(TrapReceiver):
    def _trap_callback(  # type: ignore[override]
        self,
        snmp_engine: object,
        state_reference: object,
        context_engine_id: object,
        context_name: object,
        var_binds: Iterable[tuple[object, object]],
        cb_ctx: object,
    ) -> None:
        print("state_reference:", state_reference, type(state_reference))
        msg = getattr(snmp_engine, "msgAndPduDsp", None)
        print("has msgAndPduDsp:", msg is not None)
        if msg is not None:
            get_transport_info = getattr(msg, "getTransportInfo", None)
            print("getTransportInfo callable:", callable(get_transport_info))
            if callable(get_transport_info):
                try:
                    value = get_transport_info(state_reference)
                    print("transport_info:", repr(value), type(value))
                except Exception as exc:  # noqa: BLE001
                    print("getTransportInfo error:", repr(exc))

        observer = getattr(snmp_engine, "observer", None)
        print("has observer:", observer is not None)
        if observer is not None:
            get_execution_context = getattr(observer, "getExecutionContext", None)
            print("getExecutionContext callable:", callable(get_execution_context))
            if callable(get_execution_context):
                for execution_point in [
                    "rfc3412.receiveMessage:request",
                    "rfc3412.receiveMessage:response",
                    "rfc2576.processIncomingMsg",
                    "rfc3412.prepareDataElements:sm-failure",
                ]:
                    try:
                        context = get_execution_context(execution_point)
                        if context:
                            print("ctx", execution_point, repr(context))
                    except Exception as exc:  # noqa: BLE001
                        print("ctx error", execution_point, repr(exc))

        super()._trap_callback(
            snmp_engine,
            state_reference,
            context_engine_id,
            context_name,
            var_binds,
            cb_ctx,
        )


receiver = DebugTrapReceiver(host="127.0.0.1", port=16679, community="public")
receiver.start()
print("started")
time.sleep(0.8)
subprocess.check_call(
    [
        "snmptrap",
        "-v",
        "2c",
        "-c",
        "public",
        "localhost:16679",
        "0",
        "1.3.6.1.4.1.8072.999.10",
        "1.3.6.1.4.1.8072.999.11",
        "s",
        "remote test",
    ]
)
time.sleep(1.0)
print(receiver.get_received_traps(limit=1))
receiver.stop()
