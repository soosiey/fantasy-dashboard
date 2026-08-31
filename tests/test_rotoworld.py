from fantasy_dashboard.clients.rotoworld import _PlayerNewsParser


def test_player_news_parser_captures_original_source_without_analysis() -> None:
    parser = _PlayerNewsParser()
    parser.feed(
        """
        <article class="PlayerNewsPost">
          <a href="/nfl/example-player/00112233">
            <div class="PlayerNewsPost-name-container">Example Player</div>
          </a>
          <div class="PlayerNewsPost-headline">Example headline</div>
          <time class="PlayerNewsPost-date" data-date="2026-08-30T12:00:00Z"></time>
          <div class="PlayerNewsPost-analysis">Copied article analysis.</div>
          <a href="/author/example-writer">Example Writer</a>
          <span>Source:</span><a href="https://example.com/report">Reporter</a>
        </article>
        """
    )

    assert parser.posts == [
        {
            "player_name": "Example Player",
            "title": "Example headline",
            "date": "2026-08-30T12:00:00Z",
            "author": "Example Writer",
            "source_url": "https://www.nbcsports.com/nfl/example-player/00112233",
        }
    ]
