"""Long-only attribution lane for the futures RegimeRouted strategy."""

from __future__ import annotations

import pandas as pd

from RegimeRouted import RegimeRouted


class RegimeRoutedLongOnly(RegimeRouted):
    """Keep RegimeRouted's logic while suppressing short entries."""

    can_short = False

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        if "enter_short" in dataframe:
            dataframe.loc[:, "enter_short"] = 0
        return dataframe
