# Dial or join a Hive

Give your AI any one of these:

- a GitHub repository URL;
- `owner/repository at branch`;
- a local Hive folder or declaration file;
- a seven-word chant;
- a full Dial Record ID; or
- a camera/QR/AI join card.

Useful phrases include:

- “dial this hive”
- “join this hive on this device and tell me when you are ready”
- “scan this Hive QR code and join it”

The AI first shows a plan for anything that reads the network, writes local
state, or runs verified local tooling. Approve only the complete digest shown
with that plan. GitHub joining can require a second plan after the repository's
static declaration has been verified.

The skill uses access already configured on your device. It never asks for or
prints a token, password, private key, or repository credential. A private Hive
may additionally require a QR factor after repository access succeeds. Keep
that QR payload out of chat and shell history.

Joining an ordinary supported Hive records a removable local subscription and
returns the Hive's next step as text. Unknown protocols are not run: you receive
one blocker plus the exact content-addressed material an AI would need to learn
the protocol safely.

Delete the chosen device root (normally
`~/.agent-storage/hive-hub/v1`) to remove all state created by this skill.
