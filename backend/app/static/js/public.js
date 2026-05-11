// YouFeed — minimal JS per pagine pubbliche.
// Theme toggle è inline in base.html (per evitare flash).
// Qui solo: tracking impressions su .yf-card via IntersectionObserver.

(function () {
    if (!('IntersectionObserver' in window)) return;

    var seen = new Set();
    var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var el = entry.target;
            var id = el.getAttribute('data-article-id');
            if (!id || seen.has(id)) return;
            seen.add(id);
            try {
                fetch('/yf_track', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        event_type: 'impression',
                        target_type: 'article',
                        target_id: id
                    }),
                    credentials: 'include',
                    keepalive: true
                });
            } catch (e) {}
            io.unobserve(el);
        });
    }, { threshold: 0.5 });

    document.querySelectorAll('.yf-card[data-article-id]').forEach(function (el) {
        io.observe(el);
    });
})();
