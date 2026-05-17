from app.services.ppt_artifact_service import validate_slides_html


def test_validate_slides_html_accepts_slide_class_with_state_tokens() -> None:
    html = """
    <!doctype html>
    <html>
      <body>
        <div class="deck">
          <section class="slide is-active">One</section>
          <section class="slide center tc">Two</section>
          <section class='slide dark'>Three</section>
        </div>
      </body>
    </html>
    """

    assert validate_slides_html(html)


def test_validate_slides_html_requires_deck_container() -> None:
    html = """
    <section class="slide">One</section>
    <section class="slide">Two</section>
    <section class="slide">Three</section>
    """

    assert not validate_slides_html(html)
