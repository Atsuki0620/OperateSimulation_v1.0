import streamlit as st
import pandas as pd

# functions.pyから必要な関数をインポート
from functions import (
    load_membrane_specs,       # YAMLをロード
    simulate_ro_logmean,       # ログ平均モデルでのRO計算
    append_result_to_json,     # 計算結果をJSONファイルへ追記
    load_calculation_history   # JSONファイルから履歴を読み込む
)

def main():
    st.title("RO Simulation with Log-Mean Model + JSON History Logging")

    # 1) YAMLファイルから膜スペックをロード
    specs = load_membrane_specs("membrane_specs.yaml")
    membrane_list = list(specs.keys())  # 例: ["CPA5-LD", "ESPA2-LD", "ESPA2-MAX"]

    # 2) ユーザー入力UI
    st.subheader("Input Parameters")
    selected_product = st.selectbox("Select Membrane Product", membrane_list)
    feed_flow = st.number_input("Feed Flow (m3/h)", value=30.0, min_value=0.0)
    feed_tds  = st.number_input("Feed TDS (mg/L)", value=2000.0, min_value=0.0)
    feed_press= st.number_input("Feed Pressure (bar)", value=15.5, min_value=0.0)
    temperature= st.number_input("Temperature (degC)", value=25.0, min_value=0.0)
    num_elements= st.number_input("Number of Elements per Pressure Vessel", value=4, min_value=1)

    # 3) シミュレーション実行ボタン
    if st.button("Run Simulation"):
        # 入力値をもとにRO計算を実行
        result = simulate_ro_logmean(
            feed_flow=feed_flow,
            feed_tds=feed_tds,
            feed_press=feed_press,
            temperature=temperature,
            product_name=selected_product,
            num_elements=num_elements,
            membrane_data=specs
        )

        # 結果表示
        st.subheader("Simulation Results")
        for k, v in result.items():
            st.write(f"{k}: {v}")

        # JSONファイルに計算結果を追記
        append_result_to_json(result, json_path="calculation_history.json")
        st.success("Calculation result has been saved to JSON history.")

    # 4) 履歴閲覧ボタン
    st.subheader("Calculation History")
    if st.button("View Calculation History"):
        # JSONファイルから履歴を読み込み
        history = load_calculation_history("calculation_history.json")
        if len(history) == 0:
            st.warning("No history found.")
        else:
            # pandasでDataFrameに変換し、テーブル表示
            df = pd.DataFrame(history)
            st.dataframe(df)

if __name__ == "__main__":
    main()
