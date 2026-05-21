# Wuthering Waves Echo Score Calculator — プロセスフロー

## ファイル構成

```
wuwacalc_simple/
├── wuwacalc17.py              # メインアプリ (ScoreCalculatorApp クラス)
├── config_manager.py          # 設定管理 (ConfigManager / AppConfig / UIConfig)
├── constants.py               # 定数・キャラクターデータ・テーマ色
├── dialogs.py                 # ダイアログ (CharSetting / Crop / DisplaySettings)
├── echo_data.py               # エコーデータ・スコア計算ロジック (EchoData)
├── utils.py                   # ユーティリティ (パス取得・画像クロップ・Tesseract設定)
├── languages.py               # 多言語翻訳辞書 (TRANSLATIONS)
├── config.json                # ユーザー設定 (永続化)
└── character_settings_jsons/  # キャラクター別設定ファイル (*_character.json)
```

---

## 起動フロー

```
main()
 └─ QApplication 生成
     └─ ScoreCalculatorApp.__init__()
         ├─ _init_config()          # ConfigManager.load() → AppConfig / UIConfig 復元
         ├─ _init_vars()            # UI変数初期化 (画像・タブ・キャラ名など)
         ├─ apply_theme()           # テーマ適用 (light / dark / clear)
         ├─ create_main_layout()    # UIウィジェット生成 (左右ペイン)
         └─ QTimer.singleShot(100, _post_init_setup)
              ├─ update_tabs()              # コスト設定に応じたタブ再構築
              ├─ update_ui_mode()          # OCR / 手入力モード切替
              ├─ _load_character_profiles() # JSONからキャラ読み込み
              ├─ _filter_characters_by_config() # コンボボックス絞り込み
              └─ _check_and_alert_environment() # Tesseract確認
```

---

## UI構造

```
QMainWindow (ScoreCalculatorApp)
└─ main_widget (QWidget)
    └─ main_splitter (QSplitter / Horizontal)
        ├─ 左ペイン
        │   ├─ settings_group (基本設定)
        │   │   ├─ config_combo     : コスト構成選択 (43311 / 44111)
        │   │   ├─ charcombo        : キャラクター選択
        │   │   ├─ lang_combo       : 言語選択 (ja / en / zh-TW)
        │   │   ├─ rb_manual / rb_ocr : 入力モード
        │   │   ├─ cb_auto_main     : メイン武器自動入力
        │   │   ├─ rb_batch / rb_single : 計算モード
        │   │   └─ cb_method_* (5個) : 計算手法チェックボックス
        │   ├─ button_frame (操作ボタン)
        │   │   ├─ 計算・エクスポート・全クリア・タブクリア
        │   │   └─ キャラ設定・ヘルプ・表示設定
        │   ├─ notebook (QTabWidget)
        │   │   └─ タブ×n枚 (コスト別エコー)
        │   │       ├─ main_stat_combo (メインステ選択)
        │   │       └─ sub_entries ×5 (サブステ + 数値入力)
        │   └─ result_group (計算結果 QTextEdit)
        └─ 右ペイン (QSplitter / Vertical)
            ├─ image_frame (OCRイメージ領域)
            │   ├─ btn_load / btn_paste / btn_crop
            │   ├─ クロップモード設定 (drag / percent)
            │   └─ image_label (プレビュー)
            └─ log_group (ログ QTextEdit)
```

---

## 主要処理フロー

### 1. 画像入力 → OCR → サブステ自動入力

```
[ユーザー操作]
 load_image / paste_clipboard
     └─ process_loaded_image()
         ├─ original_image 保持
         └─ apply_cropped_image()
             ├─ save_tab_image()          # タブに画像を紐付け
             ├─ display_image_preview()   # プレビュー表示
             └─ _perform_ocr()
                 ├─ _preprocess_for_ocr() # グレースケール・コントラスト強調・二値化
                 ├─ pytesseract.image_to_string (jpn+eng)
                 └─ parse_substats_from_ocr()
                     └─ on_ocr_completed()
                         └─ sub_entries に自動入力

[クロップ操作]
 perform_crop()
     ├─ percent モード → apply_percent_crop()
     └─ drag モード   → open_crop_dialog() → CropDialog
```

### 2. スコア計算

```
calculate_all_scores()
    ├─ score_mode == "single"
    │   └─ calculate_single_score()
    │       ├─ extract_substats()       # UI入力 → {stat: value} dict
    │       ├─ EchoData 生成
    │       └─ echo.evaluate_comprehensive(weights, enabled_methods)
    │           ├─ calculate_score_normalized()   # 正規化スコア
    │           ├─ calculate_score_ratio_based()  # 比率スコア
    │           ├─ calculate_score_roll_quality() # ロール品質
    │           ├─ calculate_score_effective_stats() # 有効数スコア
    │           └─ calculate_score_cv_based()     # CVスコア
    │
    └─ score_mode == "batch"
        └─ calculate_batch_scores()
            └─ 全タブを順にスコア計算 → HTML出力
```

### 3. 設定の保存・読み込み

```
[変更検知] → save_config()
    └─ _save_timer.start(500ms) ← デバウンス
        └─ actual_save_config()
            ├─ config_manager.update_app_setting(key, value) × 各設定
            └─ config_manager.save() → config.json に書き出し

[起動時] → ConfigManager.load()
    └─ AppConfig.from_dict() → validate() → 各フィールドに復元
```

### 4. キャラクター管理

```
[登録] opencharsetting()
    └─ CharSettingDialog
        └─ on_save_char()
            └─ register_char(name_jp, name_en, costkey, mainstats, weights)
                ├─ CHARACTER_STAT_WEIGHTS / CHARACTER_MAIN_STATS 更新
                ├─ _apply_character_main_stats()
                └─ _save_character_profile() → character_settings_jsons/*.json

[読み込み] _load_character_profiles()
    └─ character_settings_jsons/ をスキャン
        └─ JSON → CHARACTER_STAT_WEIGHTS / CHARACTER_MAIN_STATS に反映
            └─ _update_char_combobox()

[フィルタ] _filter_characters_by_config()
    └─ 現在のコスト構成に対応するキャラのみ表示
```

---

## EchoData クラス（スコア計算詳細）

| メソッド | 説明 |
|---|---|
| `calculate_score_normalized()` | サブステを最大値で正規化し重みを乗算 (0-100点) |
| `calculate_score_ratio_based()` | 比率×重要度の合算 (Keisan方式) |
| `calculate_score_roll_quality()` | ロール品質 (Max/Good/Low) を点数化 |
| `calculate_score_effective_stats()` | 有効サブステ数のボーナス付きスコア |
| `calculate_score_cv_based()` | CV値ベース (クリ率×2 + クリダメ + 他) |
| `evaluate_comprehensive()` | 有効メソッドの平均スコア + レーティング |

---

## 設定データ構造 (config.json)

```json
{
  "language": "ja",
  "crop_mode": "percent",
  "crop_top_percent": 35.0,
  "crop_right_percent": 25.0,
  "current_config_key": "43311",
  "character_var": "Changli",
  "mode_var": "ocr",
  "score_mode_var": "batch",
  "auto_apply_main_stats": true,
  "enabled_calc_methods": {
    "normalized": true, "ratio": true, "roll": true,
    "effective": true, "cv": true
  },
  "theme": "dark",
  "text_color": "#ffffff",
  "background_image": "",
  "background_opacity": 0.9,
  "custom_input_bg_color": "",
  "app_font": "",
  "ui": {
    "window_width": 1000,
    "window_height": 950,
    "image_preview_max_width": 600,
    "image_preview_max_height": 260
  }
}
```

---

## クロップ設定フロー（UX重点）

```
[percent モード]
  entry_top_p / entry_right_p 変更
      └─ on_crop_percent_change()
          ├─ crop_top/right_percent_var 更新
          ├─ save_config()
          └─ schedule_crop_preview()  ← 100ms デバウンス
              └─ perform_crop_preview()
                  └─ display_image_preview(クロップ済み)  ← リアルタイムプレビュー

[drag モード]
  perform_crop() → open_crop_dialog()
      └─ CropDialog (ラバーバンド選択)
          └─ OK → 座標変換 → apply_cropped_image()
```

---

## 多言語対応

- `languages.py` の `TRANSLATIONS` 辞書に `ja / en / zh-TW` を格納
- `self.tr(key)` で現在言語の文字列を取得、フォールバックは `ja`
- `retranslate_ui()` で全ウィジェットテキストを再設定
- `update_tabs()` でタブラベルも再翻訳

---

## テーマ

| テーマ | 概要 |
|---|---|
| `light` | 明るい背景 (#f0f0f0) |
| `dark` | 暗い背景 (#2e2e2e) |
| `clear` | 水色系背景 (#eefeff) |

- `DisplaySettingsDialog` でテキスト色・背景画像・不透明度・フォントを変更可能
- 設定は即時 `apply_theme()` に反映、`config.json` に保存
