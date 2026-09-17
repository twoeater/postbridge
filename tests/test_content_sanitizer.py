import unittest

from app.content import render_markdown, sanitize_html


class ContentSanitizerTests(unittest.TestCase):
    def test_script_and_event_handler_are_removed(self):
        html = sanitize_html('<script>alert(1)</script><img src="https://example.com/a.png" onerror="alert(2)">')
        self.assertNotIn('<script', html.lower())
        self.assertNotIn('onerror', html.lower())
        self.assertIn('<img', html.lower())

    def test_javascript_link_is_removed(self):
        html = render_markdown('[click](javascript:alert(1))')
        self.assertNotIn('javascript:', html.lower())
        self.assertNotIn('href=', html.lower())

    def test_data_html_link_is_removed(self):
        html = sanitize_html('<a href="data:text/html;base64,PHNjcmlwdD4=">click</a>')
        self.assertNotIn('data:text/html', html.lower())
        self.assertNotIn('href=', html.lower())

    def test_inline_png_data_image_is_preserved(self):
        html = render_markdown('![chart](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB)')
        self.assertIn('src="data:image/png;base64,', html)

    def test_inline_svg_data_image_is_removed(self):
        html = sanitize_html('<img src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=">')
        self.assertNotIn('data:image/svg+xml', html.lower())
        self.assertNotIn('src=', html.lower())

    def test_normal_https_link_is_preserved(self):
        html = render_markdown('[OpenAI](https://openai.com/)')
        self.assertIn('href="https://openai.com/"', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_table_alignment_uses_safe_align_attribute(self):
        html = render_markdown('| value |\n| ---: |\n| 123 |')
        self.assertIn('align="right"', html)
        self.assertNotIn('style=', html.lower())


if __name__ == '__main__':
    unittest.main()
