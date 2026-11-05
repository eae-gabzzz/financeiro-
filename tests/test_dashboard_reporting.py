from datetime import date

from views.dashboard import _period_items


def _month_start(months_ago: int) -> date:
    today = date.today()
    month_index = today.year * 12 + today.month - 1 - months_ago
    return date(month_index // 12, month_index % 12 + 1, 1)


def test_periodo_dos_graficos_exclui_lancamentos_fora_da_janela():
    inside = _month_start(2).isoformat()
    outside = _month_start(3).isoformat()
    items = [{"date": inside}, {"date": outside}]

    assert _period_items(items, "Últimos 3 meses") == [{"date": inside}]
    assert _period_items(items, "Todo o período") == items
