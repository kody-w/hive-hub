# Adapter source notices

The frozen summon vocabulary, derivation, and chant vectors are adapted from
`kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae`, licensed under the
MIT License, copyright 2026 RAPP Zoo v2 contributors.

The generic core and static `hive-hub-chant/1` contract reuse only that exact
owned 128-word vocabulary, with SHA-256
`325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36`.
They derive from a full Dial Record ID and require no RAPP identity or runtime.

The Payphone DoorRef field names and deterministic tether derivation reference
`kody-w/rapp-neighborhood-protocol@44e0c6eb49d619932e645fb9d9b12a5fa37f71b1`.
Hive Hub implements only the bounded read-only profile documented in this
repository.

The legacy inspector targets the historical source identity
`kody-w/RAPP_Hub@00ac2f73cade3f64c39359e9a90fca636bc387aa`. Its committed test
fixture is synthetic and contains no copied executable source.
