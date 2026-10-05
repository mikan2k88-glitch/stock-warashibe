# Queue closed-loop validation marker

This file exists only to force one safe post-upgrade Dev Queue commit so the
new executor can prove the full path:

Dev Queue -> pytest -> main commit -> explicit workflow_dispatch -> same-SHA
CI / Historical / Shadow / Runtime / Paper validation.

It contains no trading logic, credentials, broker integration, or strategy
changes.
