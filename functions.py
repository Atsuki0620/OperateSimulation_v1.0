import math
import yaml
import csv
import os
import time
from datetime import datetime

def load_membrane_specs(yaml_path: str):
    """
    YAMLファイルから膜スペック情報を読み込んで辞書を返す。
    """
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data['membranes']

def calc_element_logmean(qf_in, cf_in, pin,
                         area_m2, A_value, B_value,
                         dP_element, osm_coef):
    """
    ログ平均モデルを用いて、1エレメントの出口条件を計算する（簡易反復）。
    """
    p_out_approx = max(pin - dP_element, 0.0)

    Qp_guess = 1.0   
    Cp_guess = 50.0  

    for _ in range(5):
        Qc_guess = qf_in - Qp_guess
        salt_in = qf_in * cf_in
        salt_p  = Qp_guess * Cp_guess
        salt_c  = salt_in - salt_p
        if Qc_guess > 1e-12:
            Cc_guess = salt_c / Qc_guess
        else:
            Cc_guess = cf_in

        # ログ平均圧力
        if p_out_approx < 1e-5:
            p_out_approx = 1e-5
        p_avg = (pin - p_out_approx) / math.log(pin / p_out_approx)

        # ログ平均濃度
        if Cc_guess < 1e-5:
            Cc_guess = 1e-5
        if abs(cf_in - Cc_guess) > 1e-10:
            cf_avg = (cf_in - Cc_guess) / math.log(cf_in / Cc_guess)
        else:
            cf_avg = cf_in

        pi_f_avg = osm_coef * cf_avg
        NDP = p_avg - pi_f_avg
        if NDP < 0:
            NDP = 0.0

        A_h = A_value * 3600.0
        B_h = B_value * 3600.0

        Qp_new = A_h * NDP * area_m2  # [m3/h]
        Js = B_h * cf_avg * area_m2   # [mg/h]
        if Qp_new > 1e-12:
            Cp_new = Js / Qp_new
        else:
            Cp_new = cf_in

        Qp_guess = Qp_new
        Cp_guess = Cp_new

    Qp = Qp_guess
    Cp = Cp_guess
    Qc = qf_in - Qp
    salt_in = qf_in * cf_in
    salt_p  = Qp * Cp
    salt_c  = salt_in - salt_p
    if Qc > 1e-12:
        Cc = salt_c / Qc
    else:
        Cc = cf_in

    p_out = max(pin - dP_element, 0.0)

    return Qp, Cp, Qc, Cc, p_out

def simulate_ro_logmean(
    feed_flow,    
    feed_tds,     
    feed_press,   
    temperature,  
    product_name, 
    num_elements, 
    membrane_data 
):
    """
    ログ平均モデルで、1本の圧力容器に複数エレメント直列の場合を計算。
    """
    if product_name not in membrane_data:
        raise ValueError(f"Product '{product_name}' not found in membrane data.")

    spec = membrane_data[product_name]
    A_value = spec["A_value"]  
    B_value = spec["B_value"]  
    area_m2 = spec["area_m2"]  
    dP_element = spec["default_dP_element"]  
    osm_coef = spec["default_osm_coef"]     

    # 簡易TCF例
    ref_temp = 25.0
    factor_per_deg = 0.03
    delta_t = temperature - ref_temp
    tcf = 1.0 + factor_per_deg * delta_t
    if tcf < 0.0:
        tcf = 0.0

    A_corr = A_value * tcf
    B_corr = B_value * tcf

    q_in = feed_flow
    c_in = feed_tds
    p_in = feed_press

    total_permeate = 0.0
    total_salt_perm = 0.0

    for i in range(num_elements):
        Qp, Cp, Qc, Cc, p_out = calc_element_logmean(
            qf_in=q_in,
            cf_in=c_in,
            pin=p_in,
            area_m2=area_m2,
            A_value=A_corr,
            B_value=B_corr,
            dP_element=dP_element,
            osm_coef=osm_coef
        )
        total_permeate += Qp
        total_salt_perm += (Qp * Cp)

        q_in = Qc
        c_in = Cc
        p_in = p_out

    q_conc = q_in
    c_conc = c_in

    result = {}
    result["Selected_Product"]    = product_name
    result["FeedFlow_m3/h"]       = feed_flow
    result["FeedTDS_mg/L"]        = feed_tds
    result["Temperature_degC"]    = temperature
    result["Number_of_Elements"]  = num_elements
    result["PermeateFlow_m3/h"]   = total_permeate
    recovery = (total_permeate / feed_flow)*100.0 if feed_flow>1e-12 else 0.0
    result["Recovery_%"]          = recovery
    if total_permeate > 1e-12:
        result["PermeateTDS_mg/L"] = total_salt_perm / total_permeate
    else:
        result["PermeateTDS_mg/L"] = 0.0
    result["ConcentrateFlow_m3/h"] = q_conc
    result["ConcentrateTDS_mg/L"]  = c_conc
    result["FinalPressure_bar"]    = p_in

    return result

# ------------------------------------------------------
# ここから計算結果をCSVに保存 & 履歴参照の関数例
# ------------------------------------------------------

def append_result_to_csv(result_dict, csv_path="calculation_history.csv"):
    """
    計算結果をCSVファイルに1行追加(append)する。
    存在しない場合はヘッダ付きで新規作成。
    """
    fieldnames = [
        "Timestamp",
        "Selected_Product",
        "FeedFlow_m3/h",
        "FeedTDS_mg/L",
        "Temperature_degC",
        "Number_of_Elements",
        "PermeateFlow_m3/h",
        "Recovery_%",
        "PermeateTDS_mg/L",
        "ConcentrateFlow_m3/h",
        "ConcentrateTDS_mg/L",
        "FinalPressure_bar"
    ]

    # タイムスタンプ付与
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "Timestamp": now_str,
        "Selected_Product": result_dict.get("Selected_Product", ""),
        "FeedFlow_m3/h": result_dict.get("FeedFlow_m3/h", 0.0),
        "FeedTDS_mg/L": result_dict.get("FeedTDS_mg/L", 0.0),
        "Temperature_degC": result_dict.get("Temperature_degC", 25.0),
        "Number_of_Elements": result_dict.get("Number_of_Elements", 4),
        "PermeateFlow_m3/h": result_dict.get("PermeateFlow_m3/h", 0.0),
        "Recovery_%": result_dict.get("Recovery_%", 0.0),
        "PermeateTDS_mg/L": result_dict.get("PermeateTDS_mg/L", 0.0),
        "ConcentrateFlow_m3/h": result_dict.get("ConcentrateFlow_m3/h", 0.0),
        "ConcentrateTDS_mg/L": result_dict.get("ConcentrateTDS_mg/L", 0.0),
        "FinalPressure_bar": result_dict.get("FinalPressure_bar", 0.0)
    }

    # 追記モードでCSV出力
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        # ファイルが新規作成の場合はヘッダーを書き込む
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def load_calculation_history(csv_path="calculation_history.csv"):
    """
    計算履歴CSVをロードし、リスト of dicts あるいは
    pandas.DataFrameとして返す（ここでは簡易実装）。
    CSVが無ければ空リストを返す。
    """
    if not os.path.isfile(csv_path):
        return []

    rows = []
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return rows
