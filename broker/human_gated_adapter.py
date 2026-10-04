from __future__ import annotations


class HumanGatedRealTrialAdapter:
    def prepare(
        self,
        human_gate_package: dict,
        *,
        symbol: str | None = None,
        explicit_human_approval: bool = False,
        broker_connected: bool = False,
    ) -> dict:
        package_ready = human_gate_package.get("status") == "ready_for_review"
        checks = {
            "human_gate_package_ready": package_ready,
            "explicit_human_approval": explicit_human_approval is True,
            "broker_connected": broker_connected is True,
        }

        # This adapter deliberately never transmits a broker order.
        # Broker connection, credentials and any real order send are outside
        # automated development and require a separate Human Gate action.
        ready_for_manual = all(checks.values())
        return {
            "endpoint": "043",
            "intent_key": human_gate_package["package_key"].replace(
                "human-gate-",
                "real-trial-",
                1,
            ),
            "strategy_key": human_gate_package["strategy_key"],
            "symbol": symbol,
            "status": (
                "ready_for_manual_execution"
                if ready_for_manual
                else "blocked"
            ),
            "trial_payload": {
                "mode": "human_gated_real_trial",
                "maximum_capital_yen": (
                    human_gate_package.get("limits") or {}
                ).get("maximum_initial_capital_yen"),
                "shares_per_order": (
                    human_gate_package.get("limits") or {}
                ).get("shares_per_order"),
                "checks": checks,
                "manual_execution_required": True,
                "network_order_transmission_implemented": False,
            },
            "human_gate_package_key": human_gate_package["package_key"],
            "explicit_human_approval": explicit_human_approval,
            "broker_connected": broker_connected,
            "live_order_sent": False,
            "execution_receipt": {},
            "human_gate_required": True,
            "live_trading_allowed": False,
        }
