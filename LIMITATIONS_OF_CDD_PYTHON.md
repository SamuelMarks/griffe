# Limitations of cdd-python Integration

Replacing Griffe's native docstring parsers (`google`, `numpy`, and `sphinx`) with `cdd-python` introduces several significant regressions and limitations. While `cdd-python` successfully translates docstrings into an AST (Intermediate Representation), its feature set is strictly tailored to a subset of fields, which breaks Griffe's comprehensive extraction capabilities.

## 1. Missing Support for Extended Sections

Griffe's native parsers are designed to extract a wide array of docstring sections into specialized models (`DocstringSectionRaises`, `DocstringSectionYields`, etc.). The `cdd-python` Intermediate Representation (`IntermediateRepr`) only supports three primary keys:
- `doc`: The textual description of the object.
- `params`: The parameters/arguments.
- `returns`: The return values.

**Impact:**
Sections like `Raises`, `Yields`, `Warns`, `Examples`, `Attributes`, `Receives`, `Modules`, and `Classes` are completely unsupported as structural entities in `cdd-python`. 

If a Google-style docstring contains:
```python
Raises:
    ValueError: If something goes wrong.
```
`cdd-python` will simply append this literal text into the generic `doc` string instead of parsing it into a structured object, entirely breaking Griffe's ability to cross-reference or format exceptions.

## 2. Parser Breakage on Unsupported Sections (Numpy-style)

While Google-style extended sections are generally swallowed into the `doc` key, Numpy-style extended sections outright break the `cdd-python` parser. 

Because `cdd-python` relies heavily on heuristics rather than strict section boundary regexes (which Griffe uses), it often misinterprets unknown sections as parameter continuations.

For example, if a Numpy docstring contains:
```text
Yields
------
str
    A generated string.
```
`cdd-python` will parse this as if the function takes parameters named `Yields`, `------`, and `str`, creating a mangled `params` dictionary and corrupting the documentation output.

## 3. Sphinx Syntax Limitations

Griffe's native Sphinx parser accurately handles compound parameter type/name definitions. `cdd-python` struggles with some of these established formats.

For example, a common Sphinx pattern is:
```text
:param int foo: Description of foo.
```
Griffe successfully parses this into a parameter named `foo` with an annotation of `int`. `cdd-python` expects types and descriptions to be strictly separated (e.g., using `:type foo: int` and `:param foo: Description`). When it encounters `:param int foo:`, it frequently fails to extract `int` as the type, storing it incorrectly or missing the type entirely.

## 4. Loss of Strict Docstring Options

Griffe allows users to configure parsers (e.g., `trim_doctest_flags`, `ignore_init_summary`, `warn_unknown_params`). By offloading to `cdd-python`, we lose the granular ability to apply these Griffe-specific docstring configurations because `cdd-python` does not expose matching arguments in its `parse_docstring` API.