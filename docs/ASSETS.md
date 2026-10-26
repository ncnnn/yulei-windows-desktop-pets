# 素材包说明

## 目录结构

```
assets/default_pack/
├─ lei.png            # 雷军头像，带透明通道
├─ yu.png             # 余承东头像，带透明通道
├─ clips.json         # 17 段原声台词与逐句时间轴
├─ clips-helium.json  # 17 段 1.5 倍氦气版（与 clips.json 同 id / 角色 / 文件）
├─ pairs.json         # 8 组问答，引用 clips.json 的 id
├─ Clips/             # lei-01..09.mp3、yu-01..08.mp3（共 17）
└─ Clips-helium/      # 与 Clips 同名的 17 个氦气版
```

素材版权：随包分发的头像与音频不在 MIT 许可范围内，版权归原权利人所有；本项目仅用于学习交流与玩梗，不用于商业用途；权利人如认为使用不当，可在仓库开 issue，我们会及时移除。

## 校验规则

`manifest.load_asset_pack()` 在加载时严格校验：

- `clips.json` 覆盖 id `1..17` 且不重复，角色计数 `lei=9`、`yu=8`。
- 每段 `file` 是安全的 `.mp3` 文件名，`duration` 为正有限数。
- `lines` 非空，`start`/`end` 合法且不超过 `duration`。
- `Clips/` 与 `Clips-helium/` 中对应音频存在且非空。
- `clips-helium.json` 与 `clips.json` 的 id / 角色 / 文本 / 文件一致。
- `pairs.json` 为不重复的 `1..8`，每组 `lei`/`yu` 引用正确角色。
- `lei.png`、`yu.png` 为带透明通道的 PNG（颜色类型 4/6 或含 `tRNS`）。

任一不满足都会抛出 `AssetValidationError`，并列出全部问题。

## 应用如何查找素材

`__main__.resolve_pack()` 按顺序尝试：

1. 随包默认包：打包后 `_internal/assets/default_pack`；源码运行取仓库 `assets/default_pack`。
2. exe 同级 `assets/`（便携用户自备素材）。
3. 用户导入 store（`active_asset_root(base_dir/assets)`）。
4. 都没有则弹出导入向导（文件夹或 ZIP）。

## 替换或导入自己的素材

- 开发替换：直接修改 `assets/default_pack/` 后重新构建。
- 运行时导入：首次启动无素材时用导入向导，或删除 `%APPDATA%\LeiYuDesktopPets\assets\current.json` 后重启触发向导。导入会复制到 `base_dir/assets/packs/<uuid>` 并写入 `current.json`。

## 素材门禁

`scripts/verify_public_bundle.py` 只放行 `assets/default_pack/` 一个目录；其它位置的 `lei.png`、`yu.png`、`Clips*/`、`*.mp3`、`*.m4a` 一律拦截，避免把散落或用户私有的素材带进 Git 历史或构建产物。
