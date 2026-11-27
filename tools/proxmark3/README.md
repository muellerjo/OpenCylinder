# Proxmark3 patch: DAM grant mode

`createdelegateapp-grant-mode.patch` adds two options to the Iceman/RRG
client's `hf mfdes createdelegateapp`:

- `--enck <32 bytes hex>` — the card owner's precomputed EncK
- `--dammac <8 bytes hex>` — the card owner's precomputed DAMMAC

With both given, the client sends those values instead of computing them, so
a **site** can create its delegated application with only the owner's grant
and the DAM auth key — it never needs the owner's DAM ENC/MAC keys
([`spec/card-format.md`](../../spec/card-format.md), "DAM in practice").
Without them the command behaves exactly as before.

Made against RRG/Iceman `0bf02faa4` (2026-11-16). Apply and rebuild:

```
cd ~/proxmark3
git apply /path/to/OpenCylinder/tools/proxmark3/createdelegateapp-grant-mode.patch
make -j client
```

Used by `examples/hospital/write_test_card.py --dam SLOT --grant FILE`;
verified on a DESFire EV3 (2026-11-27).
