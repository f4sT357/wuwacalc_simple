# 修正履歴 (fixed.md)

---

## [2026-06-01] 動的キャラクターマッピングの永続化漏れ

### 対象ファイル
- `wuwacalc17.py` — `_load_character_profiles()` メソッド（1563〜1568行目付近）

### バグの概要

カスタムキャラクターを登録（`register_char`）すると、アプリ実行中は
`constants._CHAR_NAME_MAP_JP_TO_EN` / `_CHAR_NAME_MAP_EN_TO_JP` の辞書に
日英マッピングが追加される。

しかし、アプリを**再起動**すると辞書はリセットされ、
`_load_character_profiles()` は JSON ファイルから名前を読み取って
コンボボックスに追加するだけで、**辞書への書き戻しを行っていなかった**。

### 発生していた不具合

| 症状 | 原因 |
|---|---|
| キャラ選択後、UIや内部ログに英語名 (`Taoqi` 等) がそのまま表示される | `get_char_japanese_name()` が辞書を参照できずフォールバック |
| メインスタッツ自動入力がカスタムキャラ選択時に General 扱いになる | `CHARACTER_MAIN_STATS` のキー参照が英語名で失敗 |

### 修正内容

`_load_character_profiles()` 内で JSON から `en` / `jp` を取得した直後に、
`constants` の辞書へ書き戻す処理を追加。

```diff
  en = j.get('character') or j.get('EN') or ...
  jp = j.get('character_jp') or j.get('JP') or ...
+ # 再起動後もマッピングが有効になるよう constants の辞書へ書き戻す
+ from constants import _CHAR_NAME_MAP_JP_TO_EN, _CHAR_NAME_MAP_EN_TO_JP
+ _CHAR_NAME_MAP_JP_TO_EN[jp] = en
+ _CHAR_NAME_MAP_EN_TO_JP[en] = jp
  items_to_add.append((self.tr(jp), en))
```

### 補足

- `_load_character_profiles()` はアプリ起動時に必ず1回実行されるため、
  この1箇所の修正で全カスタムキャラクターのマッピング復元が保証される。
- `character_settings_jsons/` 内の JSON ファイルが存在する限り、
  再起動後もマッピングが正しく復元される。
