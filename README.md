<div align="center" style="text-align: center;">
![](dragonpilot/selfdrive/assets/dragonpilot.png)

[Read this in English](README_EN.md)

# **🐲 dragonpilot - 賦予您的愛車「龍」之魂**

**我們與您一同翱翔於更智慧、更貼心的駕駛旅程。**
</div>

## **👋 嘿, 朋友，歡迎您的到來！**

`dragonpilot` 誕生於 2019 年，由三位早期的 openpilot 華人玩家共同創立。初衷很簡單：為廣大的華人用戶、玩家們提供一個友善的交流環境、更簡便的設定協助，並加入更多適合在地使用的貼心功能。

我們深知在地化的重要性，特別是語言的親切感。因此，我們率先導入了完整的中文介面，讓 `dragonpilot` 迅速在華語地區累積了口碑，也讓華人的使用者數量在全球名列前茅。這份來自在地的支持，是我們持續前進的最大動力。

我們以功能強大的 [openpilot](https://github.com/commaai/openpilot) 為基礎——這套據美國消費者報告評測優於市售車方案的開源輔助駕駛系統——融入了更多在地化的巧思與客製化的溫度，希望能打造出最符合您需求的駕駛夥伴。(您也可以參考我們 repo 中保留的 [openpilot 原始說明檔案](README_OPENPILOT.md))

取名 `dragonpilot`，是因為我們希望它能像神話中的「龍」一樣，既強大又充滿智慧，為您的行車安全保駕護航。龍，在我們華人文化中，更是吉祥與力量的象徵，也代表著我們的根源與驕傲。

## **✨ dragonpilot 的里程碑**

我們不僅保留了 openpilot 的核心優勢，更達成了許多從社群回饋中誕生的里程碑，這些是我們引以為傲的足跡：

* **🚘 全時置中車道維持 (ALKA)**

  這不只是一個功能，更是 `dragonpilot` 的哲學。我們最早於 [0.6.2 版本](https://github.com/dragonpilot-community/dragonpilot/blob/2861467183d62151024320447ba04d18fc3fe1e6/selfdrive/car/toyota/carstate.py#L199) 時便實現了這個功能，其開發歷程始於 2017 Lexus IS300h，接著擴展至 Toyota 全車系，並逐步延伸到其他支援的品牌。它能溫柔地輔助您，讓車輛始終穩定地保持在車道中央，提供一份額外的安心與從容。

* **🌐 率先導入多國語言介面**

  在官方 openpilot 還未支援前，我們便已將多國語言介面實現。`dragonpilot` 完整支援繁體中文、簡體中文與英文，讓操作毫無隔閡。

* **💻 唯一同時支援多硬體平台**

  我們是唯一曾致力於讓專案同時兼容 EON、comma two、comma 3 與 Jetson 平台的社群分支，這份努力是為了服務最廣大的玩家社群。
  此外，在 comma.ai 團隊於 0.10.0 版本宣布停止支持 comma 3 後，我們仍是唯一一個完整同時支援 comma 3、comma 3X 以及 O3、O3L、O3XL（O3 系列為副廠硬體）的社群分支。

* **📜 曾榮獲官方認證第一大分支**

  基於活躍的社群與功能創新，`dragonpilot` 曾一度成長為 comma ai 官方認證的第一大 openpilot 分支，這份榮耀屬於每一位參與者。

## **🧑‍💻 設計理念 - 少即是多 (Less is More)**

隨著 openpilot 的 AI 模型日益強大，許多過去需要手動微調的功能，現在都已能透過更先進的模型來實現。因此，我們現在的開發重心回歸到 **「最小化修改」(minimal changes)** 的核心原則上。

我們的目標是為您提供最純粹、最接近官方的 openpilot 駕駛感受，同時保留 `dragonpilot` 那些經過時間考驗、最受社群喜愛的經典功能。我們相信，在強大的 AI 基礎上，簡潔即是力量。

## **🛠️ 硬件的足跡 - 一路走來的夥伴們**

從最早的 **EON**，到官方的 **comma two / three (C2/C3/C3X)**，再到社群中各式各樣充滿智慧的**副廠機 (如 C1.5, O2, O3, O3L, O3XL 等)**，甚至我們也曾探索過在 [**Jetson Xavier NX**](https://github.com/eFiniLan/xnxpilot) 上的可能性。

目前最新版本主要支援： comma3 / 3X 以及 O3 / O3L / O3XL 等社群硬體。
針對 EON / C1.5 / C2 等舊款硬體，最後支援的版本位於 [d2 分支](https://github.com/dragonpilot-community/dragonpilot/tree/d2)。
無論您手上是哪一款設備，都代表著您對開源駕駛輔助的一份熱情。

## **🫂 加入我們，成為「尋龍者」的一份子**

`dragonpilot` 的成長，離不開每一位使用者的貢獻與回饋。我們是一個以**公開、透明**為原則的溫暖社群，希望在這裡能與所有對 openpilot / dragonpilot 有興趣的用戶分享、交流開發與使用上的經驗。

[**歡迎加入我們的 Facebook 社團進行交流！**](https://www.facebook.com/groups/930190251238639)

## **❤️ 特別感謝**

`dragonpilot` 從創立至今，從未打算透過 Patreon 等平台進行任何形式的募資。我們的初衷是建立一個讓大家能一起學習、一起成長的社群。It's all about fun, not money.

然而，我們仍要對那些自發性支持本專案的朋友們，致上最誠摯的感謝。正是因為有您們的鼓勵，我們才有更大的動力持續前進。

[**我們的贊助者名單**](SPONSORS.md)

### **安全聲明**

`dragonpilot` 是一種駕駛**輔助**系統，並非全自動駕駛。它旨在減輕您的駕駛疲勞，提升行車安全，但駕駛人仍需時刻保持專注，並隨時準備接管車輛。請務必遵守您所在地區的交通法規。

**最後，再次感謝您的到來。**

**期待與您一同在智慧駕駛的道路上，乘「龍」而行！**

<div align="center" style="text-align: center;">

<h1>openpilot</h1>

<p>
  <b>openpilot is an operating system for robotics.</b>
  <br>
  Currently, it upgrades the driver assistance system in 300+ supported cars.
</p>

<h3>
  <a href="https://docs.comma.ai">Docs</a>
  <span> · </span>
  <a href="https://docs.comma.ai/contributing/roadmap/">Roadmap</a>
  <span> · </span>
  <a href="https://github.com/commaai/openpilot/blob/master/docs/CONTRIBUTING.md">Contribute</a>
  <span> · </span>
  <a href="https://discord.comma.ai">Community</a>
  <span> · </span>
  <a href="https://comma.ai/shop">Try it on a comma four</a>
</h3>

Quick start: `bash <(curl -fsSL openpilot.comma.ai)`

[![openpilot tests](https://github.com/commaai/openpilot/actions/workflows/tests.yaml/badge.svg)](https://github.com/commaai/openpilot/actions/workflows/tests.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![X Follow](https://img.shields.io/twitter/follow/comma_ai)](https://x.com/comma_ai)
[![Discord](https://img.shields.io/discord/469524606043160576)](https://discord.comma.ai)

</div>

<table>
  <tr>
    <td><a href="https://youtu.be/NmBfgOanCyk" title="Video By Greer Viau"><img src="https://github.com/commaai/openpilot/assets/8762862/2f7112ae-f748-4f39-b617-fabd689c3772"></a></td>
    <td><a href="https://youtu.be/VHKyqZ7t8Gw" title="Video By Logan LeGrand"><img src="https://github.com/commaai/openpilot/assets/8762862/92351544-2833-40d7-9e0b-7ef7ae37ec4c"></a></td>
    <td><a href="https://youtu.be/SUIZYzxtMQs" title="A drive to Taco Bell"><img src="https://github.com/commaai/openpilot/assets/8762862/05ceefc5-2628-439c-a9b2-89ce77dc6f63"></a></td>
  </tr>
</table>


Using openpilot in a car
------

To use openpilot in a car, you need four things:
1. **Supported Device:** a comma four, available at [comma.ai/shop/comma-four](https://www.comma.ai/shop/comma-four).
2. **Software:** The setup procedure for the comma four allows users to enter a URL for custom software. Use the URL `openpilot.comma.ai` to install the release version.
3. **Supported Car:** Ensure that you have one of [the 300+ supported cars](docs/CARS.md).
4. **Car Harness:** You will also need a [car harness](https://comma.ai/shop/car-harness) to connect your comma four to your car.

We have detailed instructions for [how to install the harness and device in a car](https://comma.ai/setup). Note that it's possible to run openpilot on [other hardware](https://blog.comma.ai/self-driving-car-for-free/), although it's not plug-and-play.


### Branches

Running `master` and other branches directly is supported, but it's recommended to run one of the following prebuilt branches:

| comma four branch      | comma 3X branch        | URL                                    | description                                                                         |
|------------------------|------------------------|----------------------------------------|-------------------------------------------------------------------------------------|
| `release-mici`         | `release-tizi`         | openpilot.comma.ai                     | This is openpilot's release branch.                                                 |
| `release-mici-staging` | `release-tizi-staging` | openpilot-test.comma.ai                | This is the staging branch for releases. Use it to get new releases slightly early. |
| `nightly`              | `nightly`              | openpilot-nightly.comma.ai             | This is the bleeding edge development branch. Do not expect this to be stable.      |
| `nightly-dev`          | `nightly-dev`          | installer.comma.ai/commaai/nightly-dev | Same as nightly, but includes experimental development features for some cars.      |

For [chestnut](https://comma.ai/shop/chestnut), use the following installer URLs:

| branch                       | URL                                                        | description                                                                         |
|------------------------------|------------------------------------------------------------|-------------------------------------------------------------------------------------|
| `release-chestnut`           | installer.comma.ai/commaai/release-chestnut                | This is openpilot's release branch.                                                 |
| `release-chestnut-staging`   | installer.comma.ai/commaai/release-chestnut-staging        | This is the staging branch for releases. Use it to get new releases slightly early. |
| `nightly-chestnut`           | installer.comma.ai/commaai/nightly-chestnut                | This is the bleeding edge development branch. Do not expect this to be stable.      |
| `nightly-chestnut-dev`       | installer.comma.ai/commaai/nightly-chestnut-dev            | Same as nightly, but includes experimental development features for some cars.      |

To start developing openpilot
------

openpilot is developed by [comma](https://comma.ai/) and by users like you. We welcome both pull requests and issues on [GitHub](http://github.com/commaai/openpilot).

* Join the [community Discord](https://discord.comma.ai)
* Check out [the contributing docs](docs/CONTRIBUTING.md)
* Check out the [openpilot tools](openpilot/tools/)
* Code documentation lives at https://docs.comma.ai
* Information about running openpilot lives on the [community wiki](https://github.com/commaai/openpilot/wiki)

Want to get paid to work on openpilot? [comma is hiring](https://comma.ai/jobs#open-positions) and offers lots of [bounties](https://comma.ai/bounties) for external contributors.

Safety and Testing
----

* openpilot observes [ISO26262](https://en.wikipedia.org/wiki/ISO_26262) guidelines, see [SAFETY.md](docs/SAFETY.md) for more details.
* openpilot has software-in-the-loop [tests](.github/workflows/tests.yaml) that run on every commit.
* The code enforcing the safety model lives in panda and is written in C, see [code rigor](https://github.com/commaai/panda#code-rigor) for more details.
* panda has software-in-the-loop [safety tests](https://github.com/commaai/panda/tree/master/tests/safety).
* Internally, we have a hardware-in-the-loop Jenkins test suite that builds and unit tests the various processes.
* panda has additional hardware-in-the-loop [tests](https://github.com/commaai/panda/blob/master/Jenkinsfile).
* We run the latest openpilot in a testing closet containing 10 comma devices continuously replaying routes.

<details>
<summary>MIT Licensed</summary>

openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.

Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.

**THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
NO WARRANTY EXPRESSED OR IMPLIED.**
</details>

<details>
<summary>User Data and comma Account</summary>

By default, openpilot uploads driving data to our servers. You can also access your data through [comma connect](https://connect.comma.ai/). We use your data to train better models and improve openpilot for everyone.

openpilot is open source software, and users can disable data collection if they wish.

openpilot logs the road-facing cameras, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver-facing camera and microphone are only logged if you explicitly opt-in in settings.

By using openpilot, you agree to [our Privacy Policy](https://comma.ai/privacy). You understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.
</details>
