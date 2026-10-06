from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def test_demo_workflow_and_margin_setting():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert [m.value for m in app.metric] == ['3', '1', '1', '0']
    assert len(app.dataframe) == 2
    app.sidebar.number_input[0].set_value(40.0).run()
    assert not app.exception
    assert app.metric[1].value == '0'
    app.text_input[0].set_value('ORG-01').run()
    assert not app.exception
    assert len(app.dataframe[1].value) == 1
