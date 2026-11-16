# Layout engines tried against ELK (vendored for the survey)

Loaded only when the page is asked for them (`?layout=dot`, `?layout=dagre`, `?layout=cola`, ...;
`layouts.js`); the default layout never loads them, and a snapshot does not carry them. Copied
unchanged from npm, pinned:

| directory  | package                  | version | licence    | file           | size   |
|------------|--------------------------|---------|------------|----------------|--------|
| graphviz/  | @hpcc-js/wasm-graphviz   | 1.30.0  | Apache-2.0 (Graphviz itself: EPL-1.0) | dist/index.js (ES module, WebAssembly inside) | 820 KB |
| dagre/     | @dagrejs/dagre           | 3.1.3   | MIT        | dist/dagre.min.js | 49 KB |
| webcola/   | webcola                  | 3.4.0   | MIT        | WebCola/cola.min.js | 80 KB |

`scripts/layout_survey.py` compares them with ELK's settings on every example and view.
