/* a graph panel's layout, off the page's thread (SPEC §4e, A graph): a Web Worker running the ELK bundle every page
   already has. In a worker, the bundle's layout engine answers ELK's own messages itself (it sets self.onmessage), once
   it is first asked for; asking for it here throws, as a worker has no worker of its own, and that is expected.
   plots-graph.js then lays out through `new ELK({ workerFactory })` */
"use strict";
importScripts("/static/elk.bundled.js");
try { new ELK(); } catch { /* (the engine is loaded: what threw is the in-page fallback, which a worker needs not) */ }
