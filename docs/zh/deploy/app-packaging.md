# App 打包

LambChat 的桌面端和移动端客户端连接已部署的后端服务。客户端不内置 Python 后端、MongoDB 或 Redis。

## 后端地址

打包前先准备公网 HTTPS 地址，例如：

```bash
export LAMBCHAT_APP_URL=https://lambchat.example.com
```

后端部署时建议设置：

```bash
APP_BASE_URL=https://lambchat.example.com
```

## 桌面端

桌面端使用 Tauri 直接打包，并和移动端共用同一个 `packaged:build` 前端构建入口。脚本会先生成 LambChat 品牌资源并构建前端静态资源，再把 `frontend/dist` 作为本地前端资源打进桌面安装包。接口地址通过 `VITE_API_BASE` 固化为 `LAMBCHAT_APP_URL`，所以安装后的桌面 App 会连接已部署的 LambChat 服务，不依赖远程网页壳。

```bash
cd frontend
LAMBCHAT_APP_URL=https://lambchat.example.com pnpm package:desktop
```

可选参数：

```bash
TAURI_BUNDLES=deb LAMBCHAT_APP_URL=https://lambchat.example.com pnpm package:desktop
TAURI_DEBUG=1 LAMBCHAT_APP_URL=https://lambchat.example.com pnpm package:desktop
```

Tauri 依赖 Rust 和对应系统依赖。Windows、macOS、Linux 安装包最好分别在对应系统或 CI runner 上构建。

## 品牌资源

打包前会生成并检查 LambChat 品牌资源：

```bash
cd frontend
pnpm brand:assets
pnpm brand:assets:check
```

生成脚本使用 `frontend/public/icons/icon-512.png` 作为品牌主图，覆盖 Android/iOS 原生图标和启动图槽位，避免安装包带默认 Capacitor 图标。发布产物文件名也会使用 `LambChat-平台-版本` 前缀。

## 移动端

移动端使用 Capacitor。前端静态资源会被打进 App，接口通过 `VITE_API_BASE` 指向 `LAMBCHAT_APP_URL`。

```bash
cd frontend
LAMBCHAT_APP_URL=https://lambchat.example.com pnpm mobile:sync
```

首次生成平台工程：

```bash
pnpm mobile:add:android
pnpm mobile:add:ios
```

打开原生工程：

```bash
pnpm mobile:open:android
pnpm mobile:open:ios
```

Android 构建需要 JDK 和 Android SDK。iOS 构建需要 macOS、Xcode 和 CocoaPods。

## Git 提交范围

`frontend/android` 和 `frontend/ios` 是 Capacitor 原生工程，建议提交到 GitHub。它们保存包名、权限、图标、启动图、Gradle/Xcode 工程配置和后续原生改动；CI 也依赖这些工程构建安装包。

不需要提交的是构建产物和本机文件，例如：

- `frontend/android/**/build/`
- `frontend/android/app/src/main/assets/public`
- `frontend/android/app/src/main/assets/capacitor*.json`
- `frontend/android/app/src/main/res/xml/config.xml`
- `frontend/android/local.properties`
- `*.apk`、`*.aab`、`*.keystore`、`*.jks`
- `frontend/ios/App/build`
- `frontend/ios/App/Pods`
- `frontend/ios/App/output`
- `frontend/ios/App/App/public`
- `frontend/ios/DerivedData`
- `frontend/ios/xcuserdata`

这些路径已由 Android/iOS 工程内的 `.gitignore` 排除；发布时只把可安装或有实际发布意义的文件上传到 GitHub Release。

## GitHub Release

推送 `v*` tag 或手动运行 `App Release` workflow 会构建并上传 Release 产物。

仓库需要配置 `LAMBCHAT_APP_URL`（Repository Variables 或 Secrets），也可以在手动运行 workflow 时填写 `app_url`。

Release 里只上传有实际发布意义的文件：

- Windows：`.msi`
- macOS：`.dmg`
- Linux：`.deb`
- Android：配置签名后上传 signed `.apk`；未配置签名时上传 debug `.apk`
- iOS：当前只在 workflow 里做工程构建检查，不上传 unsigned archive 或不可安装文件

Android 需要配置以下 Secrets 才会上传 signed APK：

```bash
ANDROID_KEYSTORE_BASE64
ANDROID_KEYSTORE_PASSWORD
ANDROID_KEY_ALIAS
ANDROID_KEY_PASSWORD
```

如果未配置 Android 签名，Android job 会跳过签名验证，把 Gradle 生成的 debug APK 上传到 Release；不会上传 release unsigned APK。

如需 iOS 可安装 `.ipa`，需要再配置 Apple 证书、provisioning profile 和导出参数；在此之前不会上传 unsigned `.xcarchive.zip`。

## Windows 用户下载

发布完成后进入 GitHub 仓库的 `Releases` 页面，下载名称类似下面的文件：

```text
LambChat-windows-v2.5.0-app-*.msi
```

这个 `.msi` 就是 Windows 安装包。其他平台文件无需下载。
