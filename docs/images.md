# Image inputs

## Experimental status

Image inputs are currently a dreamer-ready, experimental TypeSafe feature. They require explicit opt-in with `images=True`; request, answer, and limit behavior may change upstream. Do not treat this feature as production-ready. pyjev re-exports the SDK's `Image` object and forwards image requests. The official `typesafe-sdk` owns asset references, serialization, uploads, and transport.

If `images=True` is omitted, an image-bearing request may be rejected by the API. pyjev does not automatically enable the feature when it encounters an `Image` object.

## Installation and image construction

Image support requires `typesafe-sdk>=0.7.6`. Passing a path or bytes does not require an optional dependency:

```python
from pathlib import Path

from pyjev import Image

photo = Image(Path("photo.jpg"))
```

The SDK also provides `Image.from_base64(...)`. `Image.from_pil(...)` is available when Pillow is installed through the optional SDK extra:

```bash
pip install 'typesafe-sdk[pil]>=0.7.6,<1'
```

Pillow is not a pyjev or base SDK dependency.

## First image decision

```python
from pathlib import Path

from pyjev import Image, Jev

with Jev(images=True) as jev:
    result = jev.noul(
        "Is a person visible in `photo`?",
        state={"photo": Image(Path("door-camera.jpg"))},
    )

print("probability true:", result.value)
```

`NoulResult.value` is the model's probability signal for true, not a correctness guarantee. Image requests send the explicit `TypeSafe-Danger-Zone-Images: true` opt-in header through the official SDK.

## Where images can go

Pass SDK `Image` objects directly in SDK-valid structured content. pyjev preserves them; it does not recursively rewrite content or read image bytes itself. Images can be placed in state, direct primitive instructions, Noul criteria, Choice criteria, and Score levels. For example:

```python
from pathlib import Path

from pyjev import Image, Jev

candidate = Image(Path("candidate.jpg"))
red_reference = Image(Path("red.jpg"))
blue_reference = Image(Path("blue.jpg"))

with Jev(images=True) as jev:
    result = jev.choice(
        "Which reference example best matches `candidate`?",
        state={"candidate": candidate},
        choices={
            "red": red_reference,
            "blue": blue_reference,
            "other": "Neither reference",
        },
    )
```

Use structured content rather than concatenating image representations into strings. When the same image is useful to several questions, place it once in state and refer to that state path to avoid repeated image input.

## Named references with `assets=`

Use named references when the question contains a stable textual placeholder, including for a named decision:

```python
from pathlib import Path

from pyjev import Image, Jev

with Jev(images=True) as jev:
    result = jev.decide(
        "returned-product",
        state={"returned": Image(Path("returned.jpg"))},
        assets={"<catalog-photo>": Image(Path("catalog.jpg"))},
    )
```

The decision can remain portable text in `.pyjev.toml`:

```toml
[decision.returned-product]
type = "noul"
question = "Does the product in `returned` match <catalog-photo>?"
```

Supply the actual SDK `Image` in `assets=` at execution time. Do not place binary data or base64 image blobs in decision TOML. `assets=` is available on the sync and native async decision methods; see [Python API](python-api.md).

## Box localization

`Jev.box(...)` localizes one target in an image and returns a `BoxResult`. Its `box` and `value` mappings contain normalized `top`, `bottom`, `left`, and `right` edge fractions from 0 through 1 relative to the source image.

```python
from pathlib import Path
from pyjev import Image, Jev

with Jev(images=True) as jev:
    result = jev.box(
        {"target": "coffee mug", "image": "photo"},
        state={"photo": Image(Path("kitchen.jpg"))},
    )
```

Multiply horizontal coordinates by the image width and vertical coordinates by its height when pixel edges are needed:

```python
box = result.box
pixels = (
    round(box["left"] * width),
    round(box["top"] * height),
    round(box["right"] * width),
    round(box["bottom"] * height),
)
```

Box always returns one box for a target and does not return a separate not found result. For several known targets, use multiple Box questions in one bundle, with one target per question. If presence matters, add a companion Noul to the same `BundleDecision`, then interpret the Noul probability and Box coordinates separately in application policy. No universal presence or confidence threshold is provided. Box confidence is separate from coordinates and may be `None`.

Box instructions can be structured objects, for example `{"target": "mug", "image": "photo"}`. Named Box decisions and offline compilation are supported; provide runtime images through `state` or `assets=` and call `Jev(images=True)` or `AsyncJev(images=True)` for live requests. The bundled `examples/image_localization.py` demonstrates a named Box/Noul decision and optional coordinate conversion. The CLI does not upload images or execute live Box requests.

Box and image behavior are experimental upstream. TypeSafe's official SDK continues to own question schemas, image assets, serialization, and transport. Do not implement image encoding or create output crops as part of a Box call.

## Text interpolation with `attach_assets`

For advanced string interpolation, use the SDK client's `attach_assets` context manager. Direct structured placement is simpler and preferred:

```python
from pathlib import Path

from pyjev import Image, Jev

photo = Image(Path("photo.jpg"))

with Jev(images=True) as jev:
    with jev.client.attach_assets(photo):
        result = jev.noul(
            f"Is the product shown here damaged: {photo}?",
            state="returned item",
        )
```

The SDK's async client provides the same context-manager interface:

```python
from pathlib import Path

from pyjev import AsyncJev, Image

photo = Image(Path("photo.jpg"))

async with AsyncJev(images=True) as jev:
    with jev.client.attach_assets(photo):
        result = await jev.noul(
            f"Is the product shown here damaged: {photo}?",
            state="returned item",
        )
```

This is a low-level SDK feature exposed through `Jev.client`, not a separate pyjev asset registry.

## Image preparation and limits

The current TypeSafe image API accepts PNG and JPEG still images. Documented limits include:

- at most 16 MiB per image;
- each side between 280 and 1568 pixels;
- total image area between 78,400 and 2,458,624 pixels;
- a 32 MiB request-body limit and 32 MiB aggregate/expanded image limits.

The API does not apply EXIF orientation. Prepare pixels upright before sending. These limits are upstream behavior and may change; pyjev does not duplicate them with its own validator. See the [TypeSafe image documentation](https://docs.typesafe.ai/images) for current requirements and errors.

## Cost and repeated references

Image input contributes to input tokens. Reusing a reference in several places can expand the model input each time. When multiple questions use the same image, place it once in state and refer to its state path where possible.

## Named decisions and offline compilation

`compile_decision(...)` remains an offline, JSON-like request preview. It does not read image files or preview multipart data. For image-backed named decisions, compile and inspect textual placeholders such as `<catalog-photo>`, then provide the actual `Image` through `assets=` only during execution. Runtime image objects are not part of the named-decision schema or its fingerprint.

## Errors

The upstream API may reject requests when image support was not enabled, when an image format or dimensions are invalid, a named asset is not referenced, or a request exceeds size limits. Let official SDK errors retain their status, request ID, and validation details. See the [TypeSafe image documentation](https://docs.typesafe.ai/images) for current error guidance.

## Security and policy

- Visual similarity is not authentication, identity proof, or authorization.
- Confidence is a model signal, not the probability that an answer is correct.
- Images may contain sensitive data and are sent to the configured TypeSafe-compatible API.
- Apply the same data-handling and access policies used for other request content.

This initial image integration is a Python API feature. pyjev's CLI does not add image path flags or image transport.
