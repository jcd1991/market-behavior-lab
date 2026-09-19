"""Short-only attribution lane for the futures RegimeRouted strategy."""

from __future__ import annotations

import pandas as pd

from RegimeRouted import RegimeRouted


class RegimeRoutedShortOnly(RegimeRouted):
    """Keep RegimeRouted's logic while suppressing long entries."""

    can_short = True

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        if "enter_long" in dataframe:
            dataframe.loc[:, "enter_long"] = 0
        return dataframe
