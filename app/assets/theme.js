// This viewer requires the bundled local server; the HTML file itself is not runnable.
    if (location.protocol === "file:") {
      location.replace(`http://127.0.0.1:8765/${location.search}${location.hash}`);
    }
