# Horizon Valuation Comparison

Common eligible option rows: **189084**. All approaches use the same contracts, spot, DTE, rate, dividend yield, and BSM implementation.

```json
{
  "horizon_egarch|CE|ATM|31-60": {
    "n": 14577,
    "mae": 81.82836867217802,
    "rmse": 135.43003324787688,
    "mape_percent": 22.00753205246914,
    "median_absolute_error": 56.34483782611062,
    "median_absolute_percentage_error_percent": 14.120319855131253
  },
  "horizon_egarch|CE|ATM|7-30": {
    "n": 41493,
    "mae": 50.66693568896702,
    "rmse": 109.99028930836661,
    "mape_percent": 48.860759793547274,
    "median_absolute_error": 29.17074207232372,
    "median_absolute_percentage_error_percent": 14.357628808454717
  },
  "horizon_egarch|CE|ITM|31-60": {
    "n": 6644,
    "mae": 33.374405492259285,
    "rmse": 104.82968901932568,
    "mape_percent": 117.84620812412932,
    "median_absolute_error": 14.086548578072527,
    "median_absolute_percentage_error_percent": 62.22042406174868
  },
  "horizon_egarch|CE|ITM|7-30": {
    "n": 19088,
    "mae": 15.925641655344945,
    "rmse": 77.147524209232,
    "mape_percent": 393.04479161027876,
    "median_absolute_error": 3.3831898099458586,
    "median_absolute_percentage_error_percent": 91.69981036210208
  },
  "horizon_egarch|CE|OTM|31-60": {
    "n": 3412,
    "mae": 91.37429309882987,
    "rmse": 129.7337879273221,
    "mape_percent": 4.257512904237429,
    "median_absolute_error": 78.43670833926922,
    "median_absolute_percentage_error_percent": 3.3554335501610173
  },
  "horizon_egarch|CE|OTM|7-30": {
    "n": 8847,
    "mae": 54.79398189067241,
    "rmse": 92.81287035573317,
    "mape_percent": 2.932973923391904,
    "median_absolute_error": 40.433727605931836,
    "median_absolute_percentage_error_percent": 1.9871497562939937
  },
  "horizon_egarch|PE|ATM|31-60": {
    "n": 15420,
    "mae": 74.53637804313242,
    "rmse": 131.23469199169153,
    "mape_percent": 26.551255193090217,
    "median_absolute_error": 54.56507708370032,
    "median_absolute_percentage_error_percent": 18.77473067264616
  },
  "horizon_egarch|PE|ATM|7-30": {
    "n": 41423,
    "mae": 50.34147163495284,
    "rmse": 106.84998705467996,
    "mape_percent": 41.70977498812069,
    "median_absolute_error": 31.45024328953076,
    "median_absolute_percentage_error_percent": 19.753531836226763
  },
  "horizon_egarch|PE|ITM|31-60": {
    "n": 7021,
    "mae": 33.98927922051437,
    "rmse": 69.64917378273594,
    "mape_percent": 84.46518098595065,
    "median_absolute_error": 19.442185508212425,
    "median_absolute_percentage_error_percent": 82.05188255616235
  },
  "horizon_egarch|PE|ITM|7-30": {
    "n": 19067,
    "mae": 17.09656171600592,
    "rmse": 59.28710279484331,
    "mape_percent": 186.33021258723755,
    "median_absolute_error": 6.899468453542283,
    "median_absolute_percentage_error_percent": 99.42144472017169
  },
  "horizon_egarch|PE|OTM|31-60": {
    "n": 3466,
    "mae": 109.38401439475754,
    "rmse": 175.4838261941175,
    "mape_percent": 6.74162970016753,
    "median_absolute_error": 87.85586170822353,
    "median_absolute_percentage_error_percent": 4.85001415456225
  },
  "horizon_egarch|PE|OTM|7-30": {
    "n": 8626,
    "mae": 61.89627059871186,
    "rmse": 113.26677667896502,
    "mape_percent": 3.6836907132833363,
    "median_absolute_error": 41.507111739293805,
    "median_absolute_percentage_error_percent": 2.3109591480810234
  },
  "one_step_egarch|CE|ATM|31-60": {
    "n": 14577,
    "mae": 115.73281290705854,
    "rmse": 264.1232726118239,
    "mape_percent": 32.903355980550295,
    "median_absolute_error": 72.08020122526432,
    "median_absolute_percentage_error_percent": 15.143129560520762
  },
  "one_step_egarch|CE|ATM|7-30": {
    "n": 41493,
    "mae": 64.63620464059012,
    "rmse": 161.69799466347638,
    "mape_percent": 66.57879103709591,
    "median_absolute_error": 34.24667111636808,
    "median_absolute_percentage_error_percent": 16.566269263159466
  },
  "one_step_egarch|CE|ITM|31-60": {
    "n": 6644,
    "mae": 76.98839093820445,
    "rmse": 278.9109282305645,
    "mape_percent": 292.0359059403376,
    "median_absolute_error": 15.304468600350488,
    "median_absolute_percentage_error_percent": 67.60187126001958
  },
  "one_step_egarch|CE|ITM|7-30": {
    "n": 19088,
    "mae": 27.531902334243803,
    "rmse": 138.73065898673522,
    "mape_percent": 635.9260527136267,
    "median_absolute_error": 3.293143395944168,
    "median_absolute_percentage_error_percent": 94.6279853048575
  },
  "one_step_egarch|CE|OTM|31-60": {
    "n": 3412,
    "mae": 103.88562892600348,
    "rmse": 235.7100446079404,
    "mape_percent": 4.905967326388472,
    "median_absolute_error": 76.9491390001117,
    "median_absolute_percentage_error_percent": 3.277290072832949
  },
  "one_step_egarch|CE|OTM|7-30": {
    "n": 8847,
    "mae": 58.5116018101745,
    "rmse": 125.0152689448182,
    "mape_percent": 3.1640496465867667,
    "median_absolute_error": 40.03472332334559,
    "median_absolute_percentage_error_percent": 1.9704145289115294
  },
  "one_step_egarch|PE|ATM|31-60": {
    "n": 15420,
    "mae": 114.93730264391158,
    "rmse": 270.8553485649975,
    "mape_percent": 42.53583795664069,
    "median_absolute_error": 63.39030827275127,
    "median_absolute_percentage_error_percent": 21.13431911146208
  },
  "one_step_egarch|PE|ATM|7-30": {
    "n": 41423,
    "mae": 66.2558373300155,
    "rmse": 159.87877362979114,
    "mape_percent": 56.36224740273763,
    "median_absolute_error": 35.632682521256356,
    "median_absolute_percentage_error_percent": 22.67737520515287
  },
  "one_step_egarch|PE|ITM|31-60": {
    "n": 7021,
    "mae": 50.169653218082914,
    "rmse": 166.39571839058178,
    "mape_percent": 130.40884933570032,
    "median_absolute_error": 23.30843712718571,
    "median_absolute_percentage_error_percent": 92.15439066319144
  },
  "one_step_egarch|PE|ITM|7-30": {
    "n": 19067,
    "mae": 22.35296008692687,
    "rmse": 102.38560488840305,
    "mape_percent": 256.8204639441867,
    "median_absolute_error": 6.749999999986314,
    "median_absolute_percentage_error_percent": 99.80579452455713
  },
  "one_step_egarch|PE|OTM|31-60": {
    "n": 3466,
    "mae": 156.71725752429487,
    "rmse": 359.10074591013836,
    "mape_percent": 9.778584119984673,
    "median_absolute_error": 93.195969092832,
    "median_absolute_percentage_error_percent": 5.225467484551957
  },
  "one_step_egarch|PE|OTM|7-30": {
    "n": 8626,
    "mae": 74.11388716670311,
    "rmse": 168.29023687507802,
    "mape_percent": 4.40672497157417,
    "median_absolute_error": 42.56252006625289,
    "median_absolute_percentage_error_percent": 2.3920405765212025
  },
  "rolling20|CE|ATM|31-60": {
    "n": 14577,
    "mae": 97.23157384949599,
    "rmse": 113.57373708123217,
    "mape_percent": 25.907186655043223,
    "median_absolute_error": 92.28255124086411,
    "median_absolute_percentage_error_percent": 20.271907429507877
  },
  "rolling20|CE|ATM|7-30": {
    "n": 41493,
    "mae": 47.1884722419724,
    "rmse": 62.81917002304214,
    "mape_percent": 30.908345564474065,
    "median_absolute_error": 37.08385972637434,
    "median_absolute_percentage_error_percent": 18.406123380110774
  },
  "rolling20|CE|ITM|31-60": {
    "n": 6644,
    "mae": 24.259317640497656,
    "rmse": 38.46611115401241,
    "mape_percent": 69.30565205699666,
    "median_absolute_error": 14.559185177728297,
    "median_absolute_percentage_error_percent": 69.0449699838678
  },
  "rolling20|CE|ITM|7-30": {
    "n": 19088,
    "mae": 7.030931395623685,
    "rmse": 13.040733595604626,
    "mape_percent": 93.48580286891804,
    "median_absolute_error": 3.799010830080382,
    "median_absolute_percentage_error_percent": 98.49657454473329
  },
  "rolling20|CE|OTM|31-60": {
    "n": 3412,
    "mae": 78.28049241905677,
    "rmse": 96.11053378780919,
    "mape_percent": 3.5946756001316436,
    "median_absolute_error": 70.64474851887246,
    "median_absolute_percentage_error_percent": 2.82738692478377
  },
  "rolling20|CE|OTM|7-30": {
    "n": 8847,
    "mae": 46.67688186297576,
    "rmse": 62.31681545554045,
    "mape_percent": 2.4269434074278196,
    "median_absolute_error": 37.5628518061385,
    "median_absolute_percentage_error_percent": 1.822431084748979
  },
  "rolling20|PE|ATM|31-60": {
    "n": 15420,
    "mae": 63.98845027159757,
    "rmse": 81.19804120871001,
    "mape_percent": 26.9278654146896,
    "median_absolute_error": 53.904379999040756,
    "median_absolute_percentage_error_percent": 19.69636626665914
  },
  "rolling20|PE|ATM|7-30": {
    "n": 41423,
    "mae": 36.10705112211367,
    "rmse": 48.837615974872804,
    "mape_percent": 31.025042982790257,
    "median_absolute_error": 26.75436531402841,
    "median_absolute_percentage_error_percent": 17.858461443312184
  },
  "rolling20|PE|ITM|31-60": {
    "n": 7021,
    "mae": 27.246717724792997,
    "rmse": 33.25367180745749,
    "mape_percent": 80.31361732513126,
    "median_absolute_error": 22.864050357674387,
    "median_absolute_percentage_error_percent": 93.3978762149301
  },
  "rolling20|PE|ITM|7-30": {
    "n": 19067,
    "mae": 10.109816749364416,
    "rmse": 15.123598826045004,
    "mape_percent": 91.83159251011604,
    "median_absolute_error": 6.848411053798188,
    "median_absolute_percentage_error_percent": 99.70816857546302
  },
  "rolling20|PE|OTM|31-60": {
    "n": 3466,
    "mae": 94.89525385890578,
    "rmse": 111.83481461492528,
    "mape_percent": 5.7724281821420504,
    "median_absolute_error": 87.19156409125969,
    "median_absolute_percentage_error_percent": 4.780645318970053
  },
  "rolling20|PE|OTM|7-30": {
    "n": 8626,
    "mae": 49.96544888819516,
    "rmse": 66.90279083781773,
    "mape_percent": 2.991143667349845,
    "median_absolute_error": 40.44201777829869,
    "median_absolute_percentage_error_percent": 2.247785472013819
  }
}
```

MAPE and percentage errors are unstable for low observed CLOSE values; median absolute error and median absolute percentage error are reported. Results are pricing errors relative to daily CLOSE, not evidence of mispricing, arbitrage, or execution quality.
