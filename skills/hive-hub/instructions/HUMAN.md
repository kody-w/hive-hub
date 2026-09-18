# Dial or join a Hive

Give your AI any one of these:

- a GitHub repository URL;
- `owner/repository at branch`;
- a local Hive folder or declaration file;
- a seven-word chant;
- a full Dial Record ID; or
- a camera/QR/AI join card.

The public camera-AI card uses the same closed `ai-join-card` contract as the
Python core. The skill verifies its content-addressed id before using its
locator.

A chant is derived from the full Dial Record ID. You may type its seven words
with spaces and any letter case; the skill normalizes them to lowercase
hyphens. A repository slug is only a display/search alias, not a chant.
Collisions are possible, so the complete Dial Record ID must still verify.

Useful phrases include:

- “dial this hive”
- “join this hive on this device and tell me when you are ready”
- “scan this Hive QR code and join it”

The AI first shows a plan for anything that reads the network or writes local
state. Approve only the complete digest shown with that plan. Remote joining
can require a second plan after the exact declaration has been verified. The
join stage saves only a subscription and inert typed adapter plan; it never
runs repository code.

The skill uses access already configured on your device. It never asks for or
prints a token, password, private key, or repository credential. A private Hive
may additionally require a QR factor after repository access succeeds. Keep
that QR payload out of chat and shell history. The factor must be 32 random
bytes in canonical unpadded base64url form.

Joining an ordinary supported Hive records a removable local subscription and
returns the Hive's next step as text. Unknown protocols are not run: you receive
one blocker plus the exact content-addressed material an AI would need to learn
the protocol safely.

Delete the chosen device root (normally
`~/.agent-storage/hive-hub/v1`) to remove all state created by this skill.
