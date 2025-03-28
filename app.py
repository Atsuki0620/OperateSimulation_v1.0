import streamlit as st
from functions import (
    load_membrane_specs, simulate_ro_logmean,
    append_result_to_csv, load_calculation_history
)
import pandas as pd

def main():
    st.title("RO Simulation with Log-Mean Model + History Logging")

    # 1) YAMLロード
    specs = load_membrane_specs("membrane_specs.yaml")
    membrane_list = list(specs.keys())  # ex. ["CPA5-LD", "ESPA2-LD", "ESPA2-MAX"]

    # 2) ユーザー入力UI
    st.subheader("Input Parameters")
    selected_product = st.selectbox("Select Membrane Product", membrane_list)
    feed_flow = st.number_input("Feed Flow (m3/h)", value=30.0, min_value=0.0)
    feed_tds  = st.number_input("Feed TDS (mg/L)", value=2000.0, min_value=0.0)
    feed_press= st.number_input("Feed Pressure (bar)", value=15.5, min_value=0.0)
    temperature= st.number_input("Temperature (degC)", value=25.0, min_value=0.0)
    num_elements= st.number_input("Number of Elements per Pressure Vessel", value=4, min_value=1)

    # 3) シミュレーション実行
    if st.button("Run Simulation"):
        result = simulate_ro_logmean(
            feed_flow=feed_flow,
            feed_tds=feed_tds,
            feed_press=feed_press,
            temperature=temperature,
            product_name=selected_product,
            num_elements=num_elements,
            membrane_data=specs
        )
        st.subheader("Simulation Results")
        for k, v in result.items():
            st.write(f"{k}: {v}")

        # CSVに計算結果を追記
        append_result_to_csv(result, csv_path="calculation_history.csv")
        st.success("Calculation result saved to history.")

    # 4) 計算履歴の閲覧
    st.subheader("Calculation History")
    if st.button("View Calculation History"):
        history = load_calculation_history("calculation_history.csv")
        if len(history) == 0:
            st.warning("No history found.")
        else:
            # pandasでDataFrame化して表示
            df = pd.DataFrame(history)
            st.dataframe(df)


if __name__ == "__main__":
    main()
