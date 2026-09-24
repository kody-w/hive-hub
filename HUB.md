# Hive Hub

A hub for finding Hives. It is a tree of markdown cards, one fact per file: one card per Hive
protocol and one per Hive. `tools/build.py` turns the cards into views: a JSON API, a static
site and a list of chants. Nothing in the hub runs. You join a Hive with your own Brainstem, and
the hub never writes into a Hive or keeps a record of who joined.

## Who curates it

The maintainers of the kody-w/hive-hub repository. A curator adds, moves or retires a card with
one signed commit. Moving card files is how the hub is reorganized.

## Submit a card

1. Write one card file. Copy a card under `cards/` and change its fields; the builder refuses
   fields it does not know.
2. Pin exact bytes. A spec or an agent is a URL at a full commit id, with its SHA-256. A Hive
   card carries the Hive id, its first commit and the founder's key fingerprint.
3. Run `python tools/build.py` and fix whatever it refuses.
4. Send the card file to a curator by any channel, for example a pull request. A curator reviews
   it and adds it with a signed commit.

Every card is public. Never put a password, a token or a private Hive's name in one. A private
Hive can leave its address out and say in its channel how to ask.

## Where it fits

In the experimental RAPP/1 organism map, Hive Hub is the discovery part of the Hive Mind, the
network across sovereign Hives. Transport carries; signatures decide: a card, a chant or a URL
is a locator, never authority.

```text
6  You            talk to your Brainstem; confirm every exact plan
5  Brainstem      your own AI; its Hive agent joins a Hive for you
4  Your device    your copy of each Hive, one key per device per Hive
3  Hive           where members share work   <-- across: the Hive Mind (this hub)
2  Organization   the accountable body, with exactly one Hive
1  Estate         an owner's signed registry
0  RAPP/1         bytes and identity
```

The map is [ECOSYSTEM.md](https://github.com/kody-w/rapp-work/blob/experimental/rapp-work-constitution/ECOSYSTEM.md)
with the draft [CONSTITUTION.md](https://github.com/kody-w/rapp-work/blob/experimental/rapp-work-constitution/CONSTITUTION.md),
on kody-w/rapp-work branch experimental/rapp-work-constitution.

## Join a Hive

1. Dial a chant from `views/chants.txt`, or open a card.
2. Check the card's sha256 against `views/api/v2/index.json`.
3. Give the card to your Brainstem. Its Hive agent joins with the card's address, hive, root and
   founder: it clones the Hive, verifies the root and the founder fingerprint, writes one
   SSH-signed request file, and sends it the way the card's channel says.
