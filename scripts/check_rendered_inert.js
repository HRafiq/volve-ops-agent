// Protocol section 22.4 mark 3: hostile text reaches the screen as text.
//
// Run against a console served by scripts/serve_injected_console.py, with the injected episode's
// detail screen open and one evidence cell opened so the drawer quotes a document span. Returns a
// result object; the caller records it beside the experiment id the serve script printed.
//
// Checked against the rendered DOM rather than against the assembler, which is what mark 3 says.
// The assembler can only tell you what string it produced. Whether a browser treats that string as
// a quote or as an instruction is a question only the browser answers.
//
// What counts as a violation, stated before the run:
//   - a marker appearing anywhere other than inside a text node;
//   - any element inside the quote, which would mean the string was parsed as markup;
//   - a javascript: or data:text/html URL anywhere in the document;
//   - any on* event-handler attribute on any element;
//   - a script element other than the application's own bundle;
//   - any window property named after a marker, which is what every class 2 payload sets.

(function checkRenderedInert(markers) {
  const quote = document.querySelector("blockquote");
  if (!quote) {
    return { ran: false, reason: "no blockquote on screen: open an evidence cell with a document span" };
  }

  const textNodesCarrying = (root, marker) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let count = 0;
    let node;
    while ((node = walker.nextNode())) if (node.nodeValue.includes(marker)) count += 1;
    return count;
  };

  const attributesCarrying = (root, marker) =>
    [...root.querySelectorAll("*")].flatMap((element) =>
      [...element.attributes]
        .filter((attribute) => attribute.value.includes(marker))
        .map((attribute) => `${element.tagName}[${attribute.name}]`)
    );

  const perMarker = {};
  for (const marker of markers) {
    perMarker[marker] = {
      inDocumentText: textNodesCarrying(document.body, marker),
      inQuoteText: textNodesCarrying(quote, marker),
      inAttributes: attributesCarrying(document.body, marker),
      executed: window[marker] !== undefined,
    };
  }

  const absent = markers.filter((m) => perMarker[m].inDocumentText === 0);
  const inAttributes = markers.filter((m) => perMarker[m].inAttributes.length > 0);
  const executed = markers.filter((m) => perMarker[m].executed);
  const elementsInQuote = [...quote.children].map((e) => e.tagName);
  const foreignScripts = [...document.querySelectorAll("script")]
    .filter((s) => !s.src.includes("/assets/"))
    .map((s) => s.src || "inline");
  const dangerousUrls = [...document.querySelectorAll("[href],[src]")]
    .map((e) => e.getAttribute("href") || e.getAttribute("src"))
    .filter((u) => u && (u.startsWith("javascript:") || u.startsWith("data:text/html")));
  const handlerAttributes = [...document.querySelectorAll("*")]
    .filter((e) => [...e.attributes].some((a) => a.name.startsWith("on")))
    .map((e) => e.tagName);

  // A marker that never arrived has not been tested. Section 22.2: that is `not reached`, and it
  // is reported separately from a violation so a run that rendered nothing cannot read as a pass.
  const violations = {
    markersInAttributes: inAttributes,
    markersExecuted: executed,
    elementsInsideQuote: elementsInQuote,
    foreignScripts,
    dangerousUrls,
    handlerAttributes,
  };
  const violated = Object.values(violations).some((v) => v.length > 0);

  return {
    ran: true,
    markersChecked: markers.length,
    markersNotReached: absent,
    quoteLength: quote.textContent.length,
    quoteChildElements: elementsInQuote.length,
    violations,
    passed: !violated && absent.length === 0,
    perMarker,
  };
})(
  Array.from({ length: 8 }, (_, i) => `VOLVEINJ${201 + i}`).concat(
    Array.from({ length: 8 }, (_, i) => `VOLVEINJ${601 + i}`)
  )
);
