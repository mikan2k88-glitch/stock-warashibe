# Queue closed-loop validation probe v2

This probe exists only to verify the upgraded executor path:

Supabase queue -> pytest -> commit -> main -> explicit workflow_dispatch ->
same-SHA CI / Historical / Shadow / Runtime / Paper validation.

No trading logic, strategy state, broker integration, credentials, or live-order
behavior is changed by this file.
