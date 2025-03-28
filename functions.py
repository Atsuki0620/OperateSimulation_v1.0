import math
import yaml
import json
import os
from datetime import datetime

def load_membrane_specs(yaml_path: str):
    """
    YAMLファイルから膜スペック情報を読み込んで辞書を返す。
    例: data['membranes']['CPA5-LD'] -> { A_value, B_value, ... }
    """
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data['membranes']


def calc_element_logmean(qf_in, cf_in, pin,
                         area_m2, A_value, B_value,
                         dP_element, osm_coef):
    """
    ログ平均モデルを用いて、1エレメントの出口条件を計算する（簡易反復）。
    入力:
      qf_in, cf_in, pin:  エレメント入口の流量[m3/h], 塩濃度[mg/L], 圧力[bar]
      area_m2:   エレメントの有効膜面積 [m^2]
      A_value:   水透過係数 [m^3/(m^2·s·bar)]
      B_value:   塩透過係数 [m^3/(m^2·s)]
      dP_element: エレメントでの圧力損失 [bar]
      osm_coef:  浸透圧(bar)= osm_coef * TDS(mg/L) の近似係数
    出力: (Qp, Cp, Qc, Cc, p_out)
      Qp: 透過水量 [m3/h]
      Cp: 透過水塩濃度 [mg/L]
      Qc: 濃縮水量 [m3/h]
      Cc: 濃縮水塩濃度 [mg/L]
      p_out: エレメント出口圧力 [bar]
    """
    # エレメント出口圧力の初期仮定
    p_out_approx = max(pin - dP_element, 0.0)

    # 透過水量と塩濃度の初期仮定
    Qp_guess = 1.0   
    Cp_guess = 50.0  

    # 簡易的に反復して収束
    for _ in range(5):
        # 濃縮水の流量・濃度
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

        # ログ平均塩濃度
        if Cc_guess < 1e-5:
            Cc_guess = 1e-5
        if abs(cf_in - Cc_guess) > 1e-10:
            cf_avg = (cf_in - Cc_guess) / math.log(cf_in / Cc_guess)
        else:
            cf_avg = cf_in

        # 浸透圧(平均)
        pi_f_avg = osm_coef * cf_avg

        # 有効駆動力
        NDP = p_avg - pi_f_avg
        if NDP < 0:
            NDP = 0.0

        # 単位換算 (s→h)
        A_h = A_value * 3600.0
        B_h = B_value * 3600.0

        # 水透過量
        Qp_new = A_h * NDP * area_m2  # [m3/h]
        # 塩透過量
        Js = B_h * cf_avg * area_m2   # [mg/h]
        if Qp_new > 1e-12:
            Cp_new = Js / Qp_new
        else:
            Cp_new = cf_in

        Qp_guess = Qp_new
        Cp_guess = Cp_new

    # 反復後の確定値
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
    product_nameで選択した膜スペック(A, B, areaなど)を使用する。
    """
    # 1) 製品のスペックを取得
    if product_name not in membrane_data:
        raise ValueError(f"Product '{product_name}' not found in membrane data.")

    spec = membrane_data[product_name]
    A_value = spec["A_value"]  
    B_value = spec["B_value"]  
    area_m2 = spec["area_m2"]  
    dP_element = spec["default_dP_element"]  
    osm_coef = spec["default_osm_coef"]     

    # 2) 温度補正 (例: 25℃基準、1℃下がるごとに3%ダウン)
    ref_temp = 25.0
    factor_per_deg = 0.03
    delta_t = temperature - ref_temp
    tcf = 1.0 + factor_per_deg * delta_t
    if tcf < 0.0:
        tcf = 0.0
    A_corr = A_value * tcf
    B_corr = B_value * tcf

    # 3) エレメント直列計算
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


# ================================
# JSON形式での履歴管理機能
# ================================
def append_result_to_json(result_dict, json_path="calculation_history.json"):
    """
    計算結果をJSONファイルに追記する。
    - JSONファイルが存在しない場合は新規作成。
    - 既存ファイルがあれば読み込み、リストに結果をappendして再度書き込む。
    """
    # 1) 既存のJSONをロード
    if os.path.isfile(json_path):
        with open(json_path, "r", encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = []  # 新規

    # 2) タイムスタンプを付与してリストに追加
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "Timestamp": now_str,
        **result_dict  # result_dictの内容を展開
    }
    data.append(row)

    # 3) JSONに書き戻し
    with open(json_path, "w", encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_calculation_history(json_path="calculation_history.json"):
    """
    JSONファイルから計算履歴をロードし、リストで返す。
    - ファイルが無ければ空リストを返す。
    """
    if not os.path.isfile(json_path):
        return []

    with open(json_path, "r", encoding='utf-8') as f:
        data = json.load(f)

    return data
