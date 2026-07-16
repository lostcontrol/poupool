1. **Expand `docs/README.md` significantly**:
   - Add new chapters to explain fundamental pool chemistry concepts like pH, ORP (Oxidation-Reduction Potential), and how Proportional (PID-like) controllers work.
   - Include detailed architectural diagrams using Mermaid.js syntax to visualize the hardware setup (Raspberry Pi, Arduino, Relays) and state machine logic (Eco mode loop, Disinfection loop).
   - Deep dive into each component's behavior: what specific pumps/valves are activated in each mode, what speeds are used, etc.
   - Clarify the hysteresis mechanisms in Heating and Tank control.

2. **Run pre-commit steps**: `uv run pre-commit run -a` and run tests if anything else changes (though we only touch documentation).

3. **Reply to PR comments**: using `reply_to_pr_comments`.

4. **Submit**: using the original branch name `docs/user-manual-completion-16316513201850647926`.
