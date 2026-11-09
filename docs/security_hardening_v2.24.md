# v2.24 安全闭环（W4）

## 已完成

### 1. 插件安装/更新风险分级确认
- `core/plugin_risk.py`：`process`/`terminal`/`debugger` → **高**；`filesystem`/`network`/`clipboard`/`lsp` → **中**；沙箱可降一档；
- `PluginStoreDialog._confirm_risk()`：安装/更新前弹窗列权限与风险等级；**高风险默认按钮为"否"**；低风险不打扰；
- 覆盖 `_on_install` 与 `_on_update` 两条路径。

### 2. ratings.json 签名（发布 + 客户端校验）
- 发布端 `build_ratings(..., key_hex=)`：有私钥时生成 `ratings.json.sig`（Ed25519/base64），并自动加入上传列表；
- 客户端 `fetch_ratings()`：同时拉取 `.sig`，用 `QINGCAO_PLUGIN_PUBKEYS` 公钥验签；**缺失/无效签名 → 返回 None（fail-closed）**；
- 测试覆盖：签名回环、篡改拒绝、缺失签名拒绝、客户端验签取值。

### 3. 安装包签名
- `tools/sign_update_asset.py`：`--sign` 生成 `<zip>.sig`；`--verify` 校验（默认公钥 `QINGCAO_PLUGIN_PUBKEYS`）；
- `tools/ci_publish_release.py`：发布时若存在 `QINGCAO_PLUGIN_SIGN_KEY` 则自动签名、上传 `.sig` 并纳入 `RELEASE_OK` 资产校验；无密钥时保持兼容跳过；
- `release.yml` 传入 `secrets.QINGCAO_PLUGIN_SIGN_KEY`。

### 4. CI 供应链扫描
- `.github/workflows/security.yml`：`pip-audit` 扫描 `requirements.txt` 与 `requirements-linux-ci.txt`，报告上传 artifact（**非阻断初版**，待漏洞基线稳定后转强制）。

### 5. 权限矩阵测试
- `PluginAPI.run_command/run_python` 无 `process` 权限时返回 None（拒绝执行）；
- 沙箱 RPC 白名单不含 `run_command/run_python/exec/eval/shell`；
- 插件风险分级单测。

## 待办（下一批）
| 项 | 说明 |
|---|---|
| 高权限插件强制沙箱 | 当前为"显式确认为主"；下一步对 marketplace 安装的 `process` 插件强制 sandbox，并在安装 UI 显示"已沙箱"徽章 |
| Actions pin SHA | 现仍按 tag 引用 `actions/*`，建议 pin 到 commit SHA（需先核对各版本 SHA） |
| pip-audit 转强制 | 建立 CVE 基线后改为阻断 |
| 注册表重发 | 签名 ratings.json 需重发 `Publish Plugin Registry` 才生效 |
| 安装包签名公钥分发 | 客户端更新页展示签名指纹；下载后校验（当前为工具级校验） |

## 验证
```powershell
python tools/sign_update_asset.py --sign dist\QingCaoEditor-vX-windows.zip
python tools/sign_update_asset.py --verify dist\...zip --pub <公钥hex>
python -m pytest tests/test_v224_security.py tests/test_v224_update_sign.py tests/test_v223_p1_ratings.py
```
