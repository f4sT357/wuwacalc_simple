# Wuthering Waves Echo Score Calculator — プロセスフロー

## 1. ファイル構成とアーキテクチャ

`wuwacalc_simple` は、PyQt6 をベースにしたエコーのスコア計算ツールです。
バージョン17（`wuwacalc17.py`）ではモジュール化（リファクタリング）が行われ、コアロジックを別ファイルに分離しつつ、欠落時のフォールバックとして `wuwacalc17.py` 内に統合された代替メソッド（Consolidated methods）を持つ堅牢な二重構造を採用しています。

```
wuwacalc_simple/
├── wuwacalc17.py              # メインアプリケーション (QMainWindow: ScoreCalculatorApp, ScoreCalculator)
├── config_manager.py          # 設定管理 (ConfigManager / AppConfig / UIConfig)
├── constants.py               # 定数・キャラクターデータ・テーマカラー・初期データ
├── dialogs.py                 # 各種ダイアログ (CharSettingDialog / CropDialog / DisplaySettingsDialog)
├── echo_data.py               # エコーデータモデル・複数方式のスコア計算ロジック (EchoData)
├── ui_components.py           # UI構造定義 (UIComponents)
├── utils.py                   # 共通ユーティリティ (画像クロップ、Tesseract設定、パス解決)
├── languages.py               # 多言語翻訳辞書 (TRANSLATIONS ja/en/zh-TW)
├── config.json                # 永続化されたユーザー設定
├── character_settings_jsons/  # キャラクター別の個別設定ファイル (*_character.json)
└── backup_before_refactor/    # リファクタリング前のモジュール群 (フォールバック読み込み先)
    ├── app_logic.py
    ├── image_processor.py
    ├── tab_manager.py
    ├── score_calculator.py
    └── ...
```

---

## 2. 起動フロー

アプリケーション起動時の初期化およびセットアップシーケンスです。

```
main()
 └─ QApplication 生成
     └─ ScoreCalculatorApp.__init__()
         ├─ _init_config()               # 設定のロード (config.json)
         ├─ _init_vars()                 # UI制御用変数の初期化、画像プレビュー用キャッシュ生成
         ├─ QTimer の初期化 (保存デバウンス用、クロッププレビュー用、リサイズ用)
         ├─ モジュール読み込みの試行 (AppLogic, ImageProcessor, TabManager)
         │   └─ カレントディレクトリにない場合、`backup_before_refactor` からインポート (フォールバック)
         ├─ UIComponents / ScoreCalculator のインスタンス化
         ├─ ui_manager.create_main_layout()  # ウィジェット配置とレイアウト組み立て
         └─ QTimer.singleShot(100, _post_init_setup)  # 100ms 後に非同期実行
              ├─ update_tabs()                    # タブの生成 (コスト設定に応じた再構築)
              ├─ update_ui_mode()                 # 入力モード (OCR / 手入力) に応じた画像枠表示切替
              ├─ _load_character_profiles()      # JSONファイル群からキャラクタープロファイルをロード
              ├─ _filter_characters_by_config()   # 現在のコスト設定に対応するキャラをコンボボックスへ抽出
              ├─ _check_and_alert_environment()   # Pillow / Tesseract OCR 動作環境の動作可否判定
              └─ 初期キャラクター選択の適用 または メメインスタッツの自動入力 (on_character_change / _apply_character_main_stats)
```

---

## 3. UI 構造

メインウィンドウ（`QMainWindow`）内のウィジェット階層およびレイアウト構成です。

```
ScoreCalculatorApp (QMainWindow)
└─ centralWidget (ui_manager.main_widget)
    └─ main_splitter (QSplitter / 横分割)
        ├─ 左ペイン (QWidget)
        │   ├─ settings_group (QGroupBox: 基本設定)
        │   │   ├─ コスト構成選択 (QComboBox: 43311 / 44111 など)
        │   │   ├─ キャラクター選択 (QComboBox)
        │   │   ├─ 言語選択 (QComboBox: ja / en / zh-TW)
        │   │   ├─ 入力モード (QRadioButton: 手入力 / OCR) -> QButtonGroup で排他制御
        │   │   ├─ メメインスタッツ自動入力 (QCheckBox)
        │   │   ├─ 計算モード (QRadioButton: 全一括 / 選択タブのみ) -> QButtonGroup で排他制御
        │   │   └─ 計算手法 (QCheckBox×5: 正規化、比率、ロール品質、有効数、CV値)
        │   ├─ button_frame (QFrame: アクションボタン一覧)
        │   │   ├─ 計算 (score_calc.calculate_all_scores)
        │   │   ├─ テキスト出力 (export_result_to_txt)
        │   │   ├─ 全クリア (clear_all)
        │   │   ├─ タブクリア (clear_current_tab)
        │   │   ├─ キャラ設定 (opencharsetting)
        │   │   ├─ ヘルプ (README.html 表示)
        │   │   └─ 表示設定 (DisplaySettingsDialog 表示)
        │   ├─ notebook (QTabWidget: コスト別エコー入力タブ群)
        │   │   └─ 各タブ (QWidget)
        │   │       ├─ メメインスタッツ選択 (QComboBox)
        │   │       └─ サブスタッツ入力行 (QComboBox + QLineEdit) × 5組
        │   └─ result_group (QGroupBox: 計算結果表示)
        │       └─ result_text (QTextEdit / 読取専用)
        └─ 右ペイン (QSplitter / 縦分割)
            ├─ image_container (QWidget: OCR画像エリア)
            │   └─ image_frame (QGroupBox: OCRイメージ)
            │       ├─ 操作ボタン (画像読み込み / クリップボード貼り付け / クロップ実行)
            │       ├─ クロップモード (QRadioButton: ドラッグ / パーセント)
            │       ├─ クロップ座標指定 (QLineEdit: Top% / Right%) -> 入力時に自動プレビュー
            │       └─ image_label (QLabel: QScrollArea内に配置されプレビューを表示)
            └─ log_group (QGroupBox: ログ出力エリア)
                └─ log_text (QTextEdit / 読取専用)
```

---

## 4. 主要処理フロー

### 4.1 画像読み込み・リアルタイムクロップ・OCR自動入力

OCR モードにおいて、ユーザーが画像をインポートしてからエコーのサブスタッツが自動入力されるまでのプロセスです。

```
【画像入力】
ユーザー操作 (画像読込 / クリップボード貼付)
 └─ ImageProcessor.import_image() / paste_from_clipboard()
     ├─ original_image (元画像) を保持
     └─ クロップ処理へ

【リアルタイムクロップ (UX重視)】
ユーザーが Top% / Right% の数値を変更
 ├─ on_crop_percent_change()
 ├─ save_config() (自動保存の開始)
 └─ schedule_crop_preview() (100msデバウンスタイマー始動)
     └─ _update_crop_preview()
         ├─ crop_image_by_percent(original_image, top, right)
         └─ display_image_preview()  -> クロップ範囲が画像ラベルへリアルタイムに視覚反映される

【クロップの確定 & タブへの紐付け】
perform_crop() またはパーセント入力確定
 └─ apply_cropped_image(cropped_img)
     ├─ プレビュー表示を更新
     ├─ 選択中のタブがある場合: save_tab_image() でタブごとに画像を保存
     │   └─ タブ切り替え時 (on_tab_changed) に保存された画像が自動で復元表示される
     └─ なし: 警告ログを出力し、タブ選択を促す

【OCR実行】
ImageProcessor / pytesseract OCR 解析
 ├─ _preprocess_for_ocr() (グレースケール化、コントラスト強調、二値化などの高精度化)
 ├─ Tesseract OCR 実行 (jpn+eng 言語指定)
 └─ parse_substats_from_ocr() -> on_ocr_completed()
     ├─ メメインスタッツが自動検出された場合、自動入力 (auto_apply_main_stats がONの場合)
     └─ 検出されたサブスタッツの名称と数値を、現在タブの 5つの入力フィールドへ自動流し込み
```

### 4.2 スコア計算フロー

`ScoreCalculator` によるスコア算出プロセスです。

```
calculate_all_scores()
 ├─ 計算対象タブの決定 (score_mode_var に従う)
 │   ├─ 'single': 現在選択されているタブのみデータを収集
 │   └─ 'batch' (デフォルト): すべてのタブのデータを収集
 │
 ├─ タブデータの収集・クレンジング (_collect_tab_data)
 │   ├─ 各サブスタッツ入力行の名称と値を取得
 │   └─ _parse_numeric() による柔軟な数値抽出
 │       └─ 全角「％」の半角化、カンマ「,」のドット「.」変換、数値トークンの正規表現抽出
 │
 ├─ キャラクターの重み (Weights) の取得
 │   └─ 選択キャラクターに対応するステータス重みを取得 (存在しない場合は 'General')
 │
 ├─ 計算処理の実装 (calculate_batch_scores / calculate_single_score)
 │   └─ 収集されたサブスタッツの「値 × 重み」の積和計算 (Weighted-Sum)
 │       └─ score = Sum(parsed_value * weight)
 │
 └─ 結果の表示
     └─ 収集された結果を結果テキストエリア (result_text) に出力表示する
```

> [!NOTE]
> `echo_data.py` に定義された `EchoData` クラスには、正規化スコア・比率スコア・ロール品質・有効数・CV値など複数の計算メソッドおよび総合評価（SSS〜C）を出力するロジックが実装されています。現在の `wuwacalc17.py` 内の `ScoreCalculator` は、入力された数値の確実なパースと積和によるスコア算出を優先したシンプルな設計になっています。

### 4.3 設定の自動保存 (デバウンス保存)

UI 上の設定変更が即座に、かつディスク負荷をかけずに保存される仕組みです。

```
UI項目変更検知 (言語、キャラ、コスト設定、クロップパーセント等)
 └─ save_config() を呼び出し
     └─ _save_timer.start(500)  # 500msのデバウンスタイマー作動
         └─ タイマー満了時 -> actual_save_config() を実行
             ├─ メモリ上の変数を ConfigManager へ書き戻し
             └─ ConfigManager.save() が実行され、config.json へ永続化
```

---

## 5. 多言語対応とテーマ設計

### 5.1 多言語対応 (Multi-Language)

- `languages.py` に定義された辞書 `TRANSLATIONS` を利用。
- `ja` (日本語)、`en` (英語)、`zh-TW` (繁体字中国語) に対応。
- `self.tr(key)` メソッドにより、現在設定されている言語の文字列を検索・置換します。該当する翻訳キーがない場合は日本語 `ja` から補完され、それでもない場合はキー文字列自体が返るセーフティ設計です。
- 言語切り替え時は、`retranslate_ui()` によって全ラベル・プレースホルダーおよび動的に生成されたタブのラベル名が即座に再翻訳・再描画されます。

### 5.2 テーマとカスタム表示 (Themes & Style)

- `THEME_COLORS` に基づき、`light` / `dark` / `clear` の3種類のテーマをサポート。
- ユーザー設定ダイアログ (`DisplaySettingsDialog`) を介して以下の項目をカスタマイズ可能：
  - テキストカラー
  - 背景画像 (ローカルファイルパス)
  - 背景画像の不透明度 (Opacity)
  - 入力欄の背景色
  - アプリケーション全体のフォントファミリー
- 設定変更時は `apply_theme()` が即座に走り、QStyle の "Fusion" スタイルシートをベースに、CSS（RGBA、背景画像ブレンド、フォント指定等）を動的生成してアプリケーション全体に適用します。

---

## 6. バグ・障害が発生しやすい設計・実装上の注意点

本プロジェクトのコードベース（特に `wuwacalc17.py` や `ui_components.py`）を保守・改修する際、バグを引き起こしやすい脆弱な実装パターンや潜在的な不具合についてまとめます。

### 6.1 デッドコード（使われないフォールバックコード）と構文エラーの放置

*   **課題**: `wuwacalc17.py` の後半部分には、モジュール化に伴い `ui_components.py` に移行したはずの UI 構築メソッド群（`create_settings_frame` など）が「フォールバック用の複製コード」として残されています。
*   **バグの温床**:
    *   開発者が `wuwacalc17.py` 内の UI 定義コードを書き換えても、実行時には `ui_components.py` が優先してインポートされるため、**変更が一切反映されない** という混乱が生じます。
    *   さらに、`wuwacalc17.py` 内の `create_settings_frame` メソッド（1471行目付近）において、定義されていない変数 `calc_mode_layout` を使用している箇所（`settings_layout.addLayout(calc_mode_layout, ...)`）があり、**万が一フォールバックコードが実行されると実行時エラー（NameError）でクラッシュします。**
*   **対策**: 保守時は、実際の描画ロジックが `ui_components.py` 側にあることを常に意識し、フォールバック用デッドコードの不要な変更や依存を避ける必要があります。

### 6.2 デバウンス保存の「強制クローズ時」におけるデータ未保存

*   **課題**: 設定変更時の `save_config()` は、ディスク負荷軽減のために `QTimer` を用いた 500ms のデバウンス（遅延保存）を行っています。
*   **バグの温床**:
    *   ユーザーがラジオボタンの切り替えや入力値の変更を行った直後（500ms未満）にアプリケーションの閉じる「×」ボタンを押して強制終了した場合、`QTimer` が破棄されるため `actual_save_config()` が呼び出されず、**直前の変更内容が config.json に保存されません。**
*   **対策**: `ScoreCalculatorApp` クラスに `closeEvent(self, event)` をオーバーライドし、閉じる直前にタイマーがアクティブであれば強制的に `actual_save_config()` を実行する処理を追加することが推奨されます。

### 6.3 OCR数値抽出における誤検知（`_parse_numeric` の位置依存）

*   **課題**: `ScoreCalculator._parse_numeric(text)` は、正規表現 `re.search(r'[-+]?\d+[\.,]?\d*', s)` を用いて文字列から最初に見つかった数値を抽出します。
*   **バグの温床**:
    *   OCR の読み取り結果に「行番号」や「ノイズ数値」（例: `"2 クリティカル率 9.3%"` など）が混入した場合、最初に見つかる数値 `"2"` がステータス値として誤抽出されてしまいます。
*   **対策**: OCR 入力文字列をパースする際、ステータス名（エイリアス）と数値の位置関係を厳密に考慮したパースロジックへアップグレードするか、数値トークンが妥当なエコーのサブスタッツ範囲内か検証するバリデーションが必要です。

### 6.4 動的なキャラクターマッピングの永続化漏れ

*   **課題**: `register_char` にて新規キャラクターが登録されると、`constants.py` のインメモリ辞書 `_CHAR_NAME_MAP_JP_TO_EN` などに動的に追加されます。
*   **バグの温床**:
    *   これらのマッピング情報は**メモリ上にのみ保持され、`config.json` や定数ファイルへは直接保存されません。**
    *   アプリ再起動時には、`character_settings_jsons` に保存された個別プロファイルファイルを毎回スキャンしてインメモリ辞書を再構築する設計（`_load_character_profiles`）になっているため、JSON ファイルの手動削除や読み込み失敗が起きると、マッピングが完全に破損します。
*   **対策**: 動的マッピングを追加する際、プロファイルの整合性をチェックするバリデーションロジックを強化する必要があります。

### 6.5 タブ更新時の再帰シグナル発生（シグナル無限ループ）

*   **課題**: `update_tabs` の処理中、ウィジェットの削除や作成が繰り返されるため、インデックスの変更イベントなどが引き金となり PyQt のシグナルが予期せぬタイミングで送信されます。
*   **バグの温床**:
    *   `notebook.blockSignals(True)` によるシグナルの一時遮断が一部でも漏れた場合、`currentChanged` などのシグナルが再帰的にトリガーされ、意図しないデータ復元処理（`show_tab_result` 等）が走り値がクリアされる、あるいは無限ループに陥る危険があります。
*   **対策**: UI の再構築処理（タブ更新、言語切り替え、キャラ選択初期化）の開始直後と終了直後には、必ず関連ウィジェットの `blockSignals` をペアで実行し、割り込みを防ぐ必要があります。

### 6.6 重複定義による上書きと不整合

- **現象**: `wuwacalc17.py` 内に同一のメソッド名が複数箇所で定義されており、後から読み込まれた定義が前の定義を上書きします（例: `update_background_image` / `update_background_opacity` / `update_text_color` など）。参照: [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L187-L203), [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L395-L411), [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L602-L623)
- **影響**: どの実装が実行されるかが不明瞭になり、片方を修正してももう片方の定義次第で修正が反映されない。保守性の低下とバグの温床。
- **対策**: メソッド実装を一箇所に統合し、意図した箇所（`ui_components.py` か `ScoreCalculatorApp`）にのみ配置する。起動時チェックで重複定義を検出する簡易スクリプトを導入することも有効。

### 6.7 広範な例外捕捉（`except Exception` / bare `except`）とログ不足

- **現象**: 多数の `except Exception:` や bare `except:` ブロックが存在し、例外の種類やスタックトレースが埋もれるケースが見られます（例: [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L218)、[wuwacalc17.py](wuwacalc17.py#L32)、[config_manager.py](config_manager.py#L208)）。
- **影響**: 根本原因の特定が困難になり、リソース解放や再試行など適切なエラー処理が行われない恐れがあります。
- **対策**: 可能な限り具体的な例外クラスを捕捉し、最低限 `logger.exception(...)`（または `exc_info=True`）でフルスタックトレースを残す。ユーザー向けにはわかりやすいメッセージを出し、内部では詳細ログを取る運用にする。

### 6.8 起動時の致命例外処理（GUI ダイアログ表示の安全性）

- **現象**: `__main__` の致命的例外ハンドラで `QMessageBox` を直接表示していますが、`QApplication` の生成に失敗している場合などはここでさらに例外が発生する可能性があります（参照: [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L736-L751)）。
- **影響**: 起動時エラーが発生した際に二重例外となり、ログが残らなかったりプロセスが不安定になる恐れがあります。
- **対策**: GUI ダイアログ表示前に `QApplication.instance()` をチェックし、存在しない場合は標準エラー出力やログへの記録にフォールバックする。起動中の致命例外はまずログへ記録することを優先する。


### 6.6 重複定義による上書きリスク

*   **課題**: `ScoreCalculatorApp` 内の設定更新系メソッド（例: `update_background_image` / `update_background_opacity` / `update_text_color` など）がファイル内で複数回定義されており、後の定義が前の定義を上書きします。
*   **実例**:
    - [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L176-L203)
    - [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L388-L411)
    - [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L592-L623)
*   **影響**: 意図しない振る舞い（どの実装が実行されるか混乱）、保守性低下、後から追加した処理が無効化されるリスクがあります。
*   **対策**: 1箇所に実装を集約する（`UIComponents` または `ScoreCalculatorApp` のいずれか明確に）か、各メソッドを内部で共通ヘルパへ委譲して重複を排除する。

### 6.7 広範囲な例外捕捉で原因が隠れる問題

*   **課題**: プロジェクト内に多数の `except Exception:` や bare `except:` が存在します（例: 複数箇所で確認）。例外を捕捉しているもののスタックトレースがログへ残らない/表示されない場合、根本原因の特定が困難になります。
*   **実例**:
    - [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L218-L236)
    - [wuwacalc17.py](wuwacalc17.py#L32-L36)
    - [config_manager.py](config_manager.py#L208-L212)
*   **影響**: バグの再現・修正が難しくなり、不具合を潜在化させる危険があります。
*   **対策**:
    - 可能な限り具体的な例外（`ValueError`, `IOError`, `OSError`, `ImportError` 等）を捕捉する。
    - どうしても広範囲に捕捉する場合は `logger.exception(...)` を使い `exc_info=True` 相当でスタックトレースを必ず残す。
    - ユーザーへ通知する際は、内部ログ（ファイル）とユーザー向け簡潔メッセージを分離する。

### 6.8 起動時の致命例外ハンドリングに関する注意

*   **課題**: `__main__` の起動時例外ハンドラで `QMessageBox` を呼ぶ実装があり、`QApplication` の生成に失敗している状況では逆に例外を投げる可能性があります。
*   **実例**: [backup_before_refactor/wuwacalc17.py](backup_before_refactor/wuwacalc17.py#L736-L751)
*   **影響**: 既に起動失敗している状況で GUI を表示しようとしてさらにクラッシュする、もしくはヘッドレス環境でログが出力されない等の問題が発生します。
*   **対策**:
    - まずは `logging.critical(...)` 等でログファイルへ出力し、`QApplication.instance()` が存在する場合のみ `QMessageBox` を表示する。
    - CI/ヘッドレス環境ではコンソール出力やログファイルを最優先とする。

### 6.9 まとめと推奨優先度

1. 重複定義の統合（必須） — 保守性と予測可能性のため最優先で対応してください。  
2. 例外ハンドリングの見直し（高） — `logger.exception` を使ったスタックトレースの保存を徹底してください。  
3. 起動時例外の安全化（中） — GUI 非依存のフォールバックを追加してください。

必要ならこれらの修正点を自動でパッチ化して pull request 用の差分を作成します。
