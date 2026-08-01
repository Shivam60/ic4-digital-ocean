Objectie: Build a api gateway acting as a unified model router similar to open router, it must accept standardize inference schema, dynamically route it to real llm providers, proxy live streaming chunks back to the client and execute clean silet fallbacks if a primary target fails

Functional expectation, 

Unfied api & schma transation, post /v1/chat/completions endpoint that accepts a single unified payload layout, route this execution to real llm providers, if a provider access sometihng else that act as an adaptor

streaming proxy SSE, responses must be stream back to clients using server sent events, implemen precise connetion pipe streaming to relay data from upstream provider directly to client without buffering the full exectuion payload in memeory, 

if a primary target gives 429 or 502 or 503, rotuer must intercept the issue switch seamlessly to a backup provider and stream the response without cleint distrucption or surfacing errors
