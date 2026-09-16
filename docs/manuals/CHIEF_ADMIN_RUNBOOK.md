# PDEUE Chief Administrator Operating Runbook

## Sovereign Dual-Control Protocol (AUTH-01 / AUTH-02)
* **Unilateral AI Execution Prohibition:** The AI Copilot cannot place orders or alter risk parameters autonomously. All recommendations require explicit human click approval via an Action Card.
* **Order Staging:** Staging an order reserves capital immediately under conservative Quarter-Kelly bounds ($0.25 f^*$).
* **Dual Quorum Requirement:** Capital withdrawals, model parameter resets, and kill switch disengagements require two authorized cryptographic keys (Chief Administrator + Lineal Trustee).

## Emergency Circuit Breakers
* **Activation:** Trigger via the header `EMERGENCY KILL SWITCH` button or Tab 4 `TRIP BREAKER`.
* **State Change:** Instantly halts daemon loops, purges resting maker limits, and transitions the system to `KILL_SWITCH` mode.
* **Recovery:** Resetting requires dual-key authorization and a clean audit log review.
