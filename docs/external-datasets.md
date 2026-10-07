# External bearing datasets: background and provenance (verified 2026-09-25)

Scope: dataset suitability and source fault labels below describe research inputs, not cached-model support or implemented fault diagnosis. The HTTP prediction service remains FEMTO-only (D11); external adapters support offline experiments.

Compiled for the cross-dataset work (docs/cross-dataset.md). The raw data is **not** in this
repository or its git history: it lives outside the repo (`~/work/external_data/` on the build
machine) and is read through `src/bearing_pdm/ims.py` / `xjtu.py` via `adapters.py`.

Purpose: background facts for external bearing datasets considered for the RULGuard capstone.
Every fact carries a source. **UNVERIFIED** means I could not confirm it from an authoritative
source during this pass; it is *not* a claim that the fact is false.

Source keys used in the tables:

| Key | Source |
|---|---|
| [IMS-RM] | "IMS Bearing Data" readme PDF shipped with the IMS data (copy from Internet Archive item `NASA_PCoE_Bearing_Documentation`, https://archive.org/download/NASA_PCoE_Bearing_Documentation/Readme%20Document%20for%20IMS%20Bearing%20Data.pdf; local `_refs/IMS_Readme.pdf`, sha256 `cf46d37c…ae6ed`) |
| [NASA] | NASA PCoE Data Set Repository, https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ (entries 4 "Bearings" and 10 "FEMTO Bearing") |
| [QIU06] | Crossref record for DOI 10.1016/j.jsv.2005.03.007 |
| [AUD26] | Shir-Mohammad et al., "When Linear RUL Labels Disagree with Vibration Degradation…", arXiv:2607.28115 (2026), Table 5 — a secondary source that audited the IMS files |
| [SAHOO] | https://github.com/biswajitsahoo1111/data_driven_features_ims (README) — secondary source |
| [XJ-WEB] | Official XJTU-SY page by Biao Wang, https://biaowang.tech/xjtu-sy-bearing-datasets/ |
| [XJ-TR] | Wang, Lei, Li, Li, IEEE Trans. Reliability 69(1):401–412, 2020, DOI 10.1109/TR.2018.2882682 (PDF from the official MediaFire "Important References" folder; local `xjtu/_docs/Wang2020_hybrid_prognostics.pdf`) |
| [XJ-JME] | Lei, Han, Wang, Li, Yan, Yang, "XJTU-SY滚动轴承加速寿命试验数据集解读" (XJTU-SY … Datasets: A Tutorial), J. Mech. Eng. (机械工程学报) 55(16), Aug 2019, DOI 10.3901/JME.2019.16.001 (PDF from the official MediaFire folder; local `xjtu/_docs/XJTU-SY_interpretation_zh.pdf`) |
| [XJ-RM] | `ReadMe.txt` and `Download_Links_20190306.txt` in the official MediaFire folder |
| [XJ-INTRO] | `Introduction_to_XJTU-SY_Bearing_Dataset.pdf` shipped inside the official archive (sha256 `b0e0fa35…6d724f`) |
| [XJ-FILES] | My own inspection of the downloaded, hash-verified XJTU-SY files (see Download provenance) |
| [PHM12] | "IEEE PHM 2012 Prognostic Challenge" details document by FEMTO-ST (copy at https://raw.githubusercontent.com/wkzs111/phm-ieee-2012-data-challenge-dataset/master/IEEEPHM2012-Challenge-Details.pdf; local `_refs/IEEEPHM2012-Challenge-Details.pdf`) |
| [RULG] | This project's own inspection of the local FEMTO files, `data/rlguard/docs/dataset-audit.md` |
| [CWRU] | https://engineering.case.edu/bearingdatacenter/welcome and …/apparatus-and-procedures |
| [KAT] | Paderborn KAt Bearing DataCenter pages https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter (+ `/operating-conditions`, `/data-sets-and-download`) |
| [LESS16] | Lessmeier, Kimotho, Zimmer, Sextro, PHME 2016, DOI 10.36001/phme.2016.v3i1.1577 (PDF https://papers.phmsociety.org/index.php/phme/article/download/1577/542) |
| [MFPT] | MFPT "Fault Data Sets" page, Wayback snapshot 20230226220751 of https://www.mfpt.org/fault-data-sets/ (live URL now redirects to asnt.org) |

---

## 1. IMS Bearing Dataset (Univ. of Cincinnati / NASA PCoE)

| Fact | Value | Source |
|---|---|---|
| Institution | NSF I/UCR Center for Intelligent Maintenance Systems (IMS), with support from Rexnord Corp., Milwaukee WI | [IMS-RM]; [NASA] ("provided by the Center for Intelligent Maintenance Systems (IMS), University of Cincinnati") |
| Dataset authors (as NASA cites them) | J. Lee, H. Qiu, G. Yu, J. Lin, and Rexnord Technical Services (2007) | [NASA] |
| Official source | NASA PCoE repository, item "4. Bearings": https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip (1,075,597,174 bytes; S3 Last-Modified 2022-09-18). The zip contains a single `4. Bearings/IMS.7z` (1,075,320,408 bytes) — listed via HTTP range requests, not downloaded by me | [NASA]; HTTP HEAD + zip central directory |
| Original publication | H. Qiu, J. Lee, J. Lin, G. Yu, "Wavelet filter-based weak signature detection method and its application on rolling element bearing prognostics", J. Sound Vib. 289(4–5):1066–1090, Feb 2006, DOI 10.1016/j.jsv.2005.03.007. (The readme lists only Qiu, Lee, Lin and the title "…Roller Bearing Prognostics"; Crossref lists four authors.) | [QIU06]; [IMS-RM] |
| Purpose | Test-to-failure experiments ("Each data set describes a test-to-failure experiment") | [IMS-RM] |
| Tests / bearings | 3 data sets; 4 bearings on one shaft per test (12 bearing-runs total) | [IMS-RM] |
| Bearing type | Rexnord ZA-2115 double-row bearings | [IMS-RM] |
| Sensors | PCB 353B33 High Sensitivity Quartz ICP accelerometers on the bearing housing; set 1: two per bearing (x and y), sets 2 and 3: one per bearing. DAQ: NI DAQ Card 6062E | [IMS-RM] |
| Sampling frequency | 20 kHz | [IMS-RM] |
| Samples per file / duration | 20,480 points per file; readme calls each file a "1-second" snapshot (20,480 / 20,000 Hz = 1.024 s) | [IMS-RM] |
| Recording interval | Set 1: every 10 min, except the first 43 files every 5 min. Sets 2, 3: every 10 min. Larger gaps in the file-name timestamps mean the experiment resumed the next working day | [IMS-RM] |
| Speed | 2000 RPM constant (AC motor, rub belts) | [IMS-RM] |
| Load | 6000 lbs radial, by a spring mechanism; all bearings force-lubricated | [IMS-RM] |
| Set 1 | 2003-10-22 12:06:24 to 2003-11-25 23:39:56; 2,156 files; 8 channels: B1 = ch1 and ch2, B2 = ch3 and ch4, B3 = ch5 and ch6, B4 = ch7 and ch8 | [IMS-RM] |
| Set 2 | 2004-02-12 10:32:39 to 2004-02-19 06:22:39; 984 files; 4 channels: B1–B4 = ch1–ch4 | [IMS-RM] |
| Set 3 | 2004-03-04 09:27:46 to 2004-04-04 19:01:57; 4,448 files; 4 channels: B1–B4 = ch1–ch4 | [IMS-RM] |
| Failures at end of test | Set 1: inner race defect in bearing 3, roller element defect in bearing 4. Set 2: outer race failure in bearing 1. Set 3: outer race failure in bearing 3 | [IMS-RM] |
| Failure definition / stop criterion | **No explicit stop criterion is stated.** The readme says only "All failures occurred after exceeding designed life time of the bearing which is more than 100 million revolutions." | [IMS-RM] |
| Run-to-failure | Yes, per the readme ("test-to-failure"). Only 4 documented failed bearings across 3 runs; the other 8 bearing-runs end without a documented failure (right-censored) | [IMS-RM] |
| RUL suitability | Usable, but n = 4 failed trajectories, one operating condition, and no stop criterion. Treat as small external validation, not a training corpus. The file timestamps give elapsed time, so RUL labels can be built for the failed bearings | derived from [IMS-RM] |
| File format / columns | ASCII, one file per snapshot, file name = timestamp, one row per sample, one column per channel (8 in set 1, 4 in sets 2 and 3) | [IMS-RM] |
| Folder layout (Set 3 = `4th_test/txt`) | **Verified locally (2026-09-25)** on the official NASA archive (zip sha256 recorded in `~/work/external_data/ims/bearings.zip.sha256`): `IMS.7z` -> `1st_test.rar`, `2nd_test.rar`, `3rd_test.rar`; extracting them gives `1st_test/` (2,156 files), `2nd_test/` (984 files) and `4th_test/txt/` (the set-3 data). Files are tab-separated with CRLF line endings | local inspection |
| Set-3 count mismatch | **Verified locally:** `4th_test/txt` holds **6,324 files, 2004-03-04 09:27:46 -> 2004-04-18 02:42:55**, not the readme's 4,448 ending 2004-04-04 19:01:57 (sets 1 and 2 match the readme exactly). File #4,448 on disk is exactly 2004-04-04 19:01:57, the readme's documented end, so the readme describes a prefix of the archive and the 1,876 later files are undocumented. This project **truncates set 3 at the documented end** (`ims.IMS_DOCUMENTED_END`): the documented outer-race failure is anchored to the documented end of test, not to 13 further undocumented days (docs/decisions.md D25) | local inspection; [AUD26] reports the same |
| "Test 3 shows no clear degradation" | **UNVERIFIED.** This is usually attributed to Gousseau, Antoni, Girardin, Griffaton, "Analysis of the Rolling Element Bearing data set of the Center for Intelligent Maintenance Systems of the University of Cincinnati", CM2016 (HAL hal-01715193; metadata confirmed via the HAL API). HAL returned an anti-bot page, so I could not read the claim. [AUD26] treats the extended set-3 directory as "exploratory only" because of the file-count mismatch | HAL API; [AUD26] |
| Units of vibration values | **UNVERIFIED.** The readme gives no units (neither g nor volts). Do not assume g without checking against the 353B33 sensitivity | [IMS-RM] (silent) |
| License / terms | No explicit license. NASA asks: "Publications making use of databases obtained from this repository are requested to acknowledge both the assistance received by using this repository and the donators of the data." | [NASA] |

Citation:
```
@misc{ims_bearing_2007,
  author = {Lee, J. and Qiu, H. and Yu, G. and Lin, J. and {Rexnord Technical Services}},
  title  = {Bearing Data Set},
  howpublished = {IMS, University of Cincinnati. NASA Prognostics Data Repository, NASA Ames Research Center, Moffett Field, CA},
  year   = {2007},
  url    = {https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip}}
@article{qiu2006wavelet,
  author = {Qiu, Hai and Lee, Jay and Lin, Jing and Yu, Gang},
  title  = {Wavelet filter-based weak signature detection method and its application on rolling element bearing prognostics},
  journal = {Journal of Sound and Vibration}, volume = {289}, number = {4--5}, pages = {1066--1090}, year = {2006},
  doi = {10.1016/j.jsv.2005.03.007}}
```

---

## 2. XJTU-SY Bearing Datasets

| Fact | Value | Source |
|---|---|---|
| Institution | Institute of Design Science and Basic Component, Xi'an Jiaotong University (XJTU), and Changxing Sumyoung Technology Co., Ltd. (SY), Zhejiang | [XJ-WEB]; [XJ-JME] |
| Authors | Paper: Biao Wang, Yaguo Lei, Naipeng Li, Ningbo Li. Tutorial: Yaguo Lei, Tianyu Han, Biao Wang, Naipeng Li, Tao Yan, Jun Yang. Dataset maintainer: Biao Wang (contact via the official page) | [XJ-TR]; [XJ-JME]; [XJ-RM] |
| Official source | https://biaowang.tech/xjtu-sy-bearing-datasets/. It links Google Drive, Dropbox, MediaFire, MEGA and Baidu; `Download_Links_20190306.txt` also lists Tencent Weiyun | [XJ-WEB]; [XJ-RM] |
| Original publication | IEEE Trans. Reliability 69(1):401–412, 2020 (manuscript accepted Nov 2018, early access 2018), DOI 10.1109/TR.2018.2882682 | [XJ-TR]; Crossref |
| Purpose | Accelerated degradation (life) tests. "anyone can use them to validate prognostics algorithms of rolling element bearings" | [XJ-WEB] |
| Number of bearings | 15, with 5 per operating condition | [XJ-WEB]; [XJ-TR]; [XJ-JME] Table 3 |
| Bearing type | LDK UER204. Tutorial Table 1: inner-race diameter 29.30 mm, outer-race diameter 39.80 mm, pitch diameter 34.55 mm, ball diameter 7.92 mm, 8 balls, contact angle 0°, basic dynamic load rating 12,820 N, basic static load rating 6.65 kN | [XJ-TR]; [XJ-JME] |
| Operating conditions | C1: 2100 rpm (35 Hz), 12 kN. C2: 2250 rpm (37.5 Hz), 11 kN. C3: 2400 rpm (40 Hz), 10 kN. Load is radial and applied in the horizontal direction by a hydraulic system | [XJ-WEB]; [XJ-JME] Table 2; [XJ-TR] |
| Sensors | Two PCB 352C33 (single-axis) accelerometers at 90° to each other, one horizontal and one vertical, on the bearing housing (magnetic base). DAQ: DT9837 | [XJ-TR]; [XJ-JME] |
| Sampling frequency | 25.6 kHz | [XJ-TR]; [XJ-JME] |
| Samples per record / duration | 32,768 samples (1.28 s) | [XJ-TR]; [XJ-WEB] |
| Recording interval | Every 1 min | [XJ-TR]; [XJ-JME] |
| Run-to-failure | Yes, "complete run-to-failure data of 15 rolling element bearings" | [XJ-WEB] |
| Stop criterion (**the two sources disagree**) | **TR paper:** "the accelerated degradation tests of bearings are stopped when the amplitude of the vibration signal is higher than 20 g for security reasons … the time when the amplitude … exceeds 20 g is considered as the failure time". **JME tutorial §3.2** (translated): a relative threshold is used; a bearing is considered completely failed, and the test is stopped immediately, when "the maximum amplitude of the horizontal or vertical vibration signal exceeds 10×A_h, where A_h is the maximum amplitude of the bearing in the normal operating stage". It adds that under the relative threshold some bearings reach amplitudes up to 50 g, so users may adjust the failure threshold for their own problem. **The dataset's own intro PDF:** "each of the accelerated degradation tests was performed until the maximum amplitude of the horizontal or vertical vibration signals exceeded 10×Ah, where Ah is the maximum amplitude of the horizontal or vertical vibration signals in the normal operating stage." So the dataset documentation uses 10×A_h; the 20 g figure appears only in the TR paper. **Observed [XJ-FILES]:** in each bearing's final file, max\|x\| on the worse axis ranges from 25.7 g (3_4) to 54.4 g (1_4). The lowest per-axis final maximum is 20.1 g (2_2, vertical). Every bearing therefore ends above 20 g on at least one axis, consistent with both statements | [XJ-TR] §IV-A; [XJ-JME] §3.2; [XJ-INTRO]; [XJ-FILES] |
| Per-bearing data (tutorial Table 3): files, actual life, failed element | 1_1: 123 files, 2 h 3 min, outer race · 1_2: 161, 2 h 41 min, outer race · 1_3: 158, 2 h 38 min, outer race · 1_4: 122, 2 h 2 min, cage · 1_5: 52, 52 min, inner race + outer race · 2_1: 491, 8 h 11 min, inner race · 2_2: 161, 2 h 41 min, outer race · 2_3: 533, 8 h 53 min, cage · 2_4: 42, 42 min, outer race · 2_5: 339, 5 h 39 min, outer race · 3_1: 2538, 42 h 18 min, outer race · 3_2: 2496, 41 h 36 min, inner race + ball + cage + outer race · 3_3: 371, 6 h 11 min, inner race · 3_4: 1515, 25 h 15 min, inner race · 3_5: 114, 1 h 54 min, outer race. L10 range per condition: C1 5.600–9.677 h, C2 6.786–11.726 h, C3 8.468–14.632 h | [XJ-JME] Table 3; file counts cross-checked in [XJ-FILES] |
| Failure modes observed | Inner race wear, cage fracture, outer race wear, outer race fracture | [XJ-WEB]; [XJ-JME] Fig. 3 |
| RUL suitability | Good: 15 complete trajectories, 3 conditions, documented failed element for each bearing. Caveats: accelerated tests, 5 bearings per condition, and the failure threshold is ambiguous (20 g vs 10×A_h) | derived |
| File/folder structure | One CSV per 1-min sample, named `1.csv … N.csv` in time order. Column 1 = horizontal vibration, column 2 = vertical vibration | [XJ-JME] §1.3; see Download provenance for the observed tree |
| CSV header | `Horizontal_vibration_signals,Vertical_vibration_signals` — see observed first lines below | [XJ-FILES] |
| Units | Acceleration in g: the [XJ-INTRO] signal plots label the y-axis "Amplitude (g)", and the paper states thresholds in g. The CSV header carries no unit. First-file peaks of 1.7–5.8 g are consistent with g | [XJ-INTRO]; [XJ-TR]; [XJ-FILES] |
| License / terms | No formal license. "These datasets are publicly available and anyone can use them to validate prognostics algorithms … Publications making use of the XJTU-SY bearing datasets are requested to cite the following paper." | [XJ-WEB] |

Citation:
```
@article{wang2020hybrid,
  author  = {Wang, Biao and Lei, Yaguo and Li, Naipeng and Li, Ningbo},
  title   = {A Hybrid Prognostics Approach for Estimating Remaining Useful Life of Rolling Element Bearings},
  journal = {IEEE Transactions on Reliability}, volume = {69}, number = {1}, pages = {401--412}, year = {2020},
  doi     = {10.1109/TR.2018.2882682}}
@article{lei2019xjtusy,
  author  = {Lei, Yaguo and Han, Tianyu and Wang, Biao and Li, Naipeng and Yan, Tao and Yang, Jun},
  title   = {{XJTU-SY} Rolling Element Bearing Accelerated Life Test Datasets: A Tutorial},
  journal = {Journal of Mechanical Engineering (Jixie Gongcheng Xuebao)}, volume = {55}, number = {16}, year = {2019},
  doi     = {10.3901/JME.2019.16.001}, note = {In Chinese}}
```

---

## 3. FEMTO / PRONOSTIA (IEEE PHM 2012), brief

| Fact | Value | Source |
|---|---|---|
| Institution | FEMTO-ST Institute (UMR CNRS 6174), Besançon, France; PRONOSTIA platform | [PHM12]; [NASA] |
| Publication | P. Nectoux, R. Gouriveau, K. Medjaher, E. Ramasso, B. Morello, N. Zerhouni, C. Varnier, "PRONOSTIA: An Experimental Platform for Bearings Accelerated Degradation Tests", IEEE Int. Conf. PHM, Denver, 2012. [PHM12] and [NASA] give the title as "…Accelerated Life Test"; HAL hal-00719503 uses "…Degradation Tests" | [PHM12]; [NASA] |
| Official source | https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip | [NASA] |
| Purpose | Prognostics (RUL) challenge; run-to-failure accelerated degradation | [PHM12] |
| Bearings | 17 in the challenge: 6 learning (1_1, 1_2, 2_1, 2_2, 3_1, 3_2) and 11 truncated test bearings | [PHM12] Table 1 |
| Bearing model | **UNVERIFIED** (not named in [PHM12]). Geometry from [PHM12] A.1: outer diameter 32 mm, bore 20 mm, width 7 mm, static rating 2470 N, dynamic rating 4000 N, 13 rolling elements of 3.5 mm | [PHM12] |
| Conditions | 1800 rpm and 4000 N; 1650 rpm and 4200 N; 1500 rpm and 5000 N | [PHM12] §3.2 |
| Sensors | 2 DYTRAN 3035B accelerometers (horizontal and vertical, ±50 g, 100 mV/g) plus an RTD PT100 temperature probe | [PHM12] §2, A.2 |
| Sampling | Vibration: 25.6 kHz, 2560 samples (0.1 s) every 10 s. Temperature: 10 Hz, 600 samples per minute (§4.1; §2 says 0.1 Hz, an internal inconsistency) | [PHM12] |
| Stop criterion | Tests stopped when the vibration amplitude exceeded 20 g; "RUL was defined as time to accelerometer exceeding 20g" | [PHM12] §3.1, Note 1 |
| Failure modes | Not labelled: "no assumption on the type of failure … balls, inner or outer races, cage" | [PHM12] |
| Files | `acc_xxxxx.csv` columns: hour, minute, second, µs, horizontal accel, vertical accel. `temp_xxxxx.csv` columns: hour, minute, second, 0.x s, RTD. Some temperature files use `;` as the delimiter | [PHM12] Table 2; [RULG] |
| RUL suitability | Yes (this project's primary dataset) | — |
| Terms | Cite Nectoux et al. 2012 (requested in [PHM12]); NASA acknowledgement request as for IMS | [PHM12]; [NASA] |

---

## 4. Diagnosis-oriented datasets, brief

| Dataset | Key facts | Run-to-failure? | RUL usable? | Source |
|---|---|---|---|---|
| **CWRU** (Case Western Reserve Univ. Bearing Data Center) | Single-point faults seeded by EDM, 0.007–0.040 in diameter, on inner race, ball and outer race. Drive-end and fan-end bearings (SKF; NTN equivalents for 28 and 40 mil faults). Motor loads 0–3 hp (1797–1720 rpm), 2 hp motor. Sampling 12 kHz, plus 48 kHz for drive-end faults. Accelerometers at 12 o'clock on the drive end and fan end. `.mat` files | No. Seeded faults, short steady-state recordings | No | [CWRU] |
| **Paderborn KAt** | 32 ball bearings of type 6203: 6 healthy, 12 with artificial damage, 14 with real damage from accelerated lifetime tests. Motor current and vibration sampled at 64 kHz. 4 settings: base 1500 rpm, 0.7 Nm, 1000 N, with one parameter reduced per setting to 900 rpm, 0.1 Nm or 400 N. 20 × 4 s measurements per setting. `.mat` files, e.g. `N15_M07_F10_KA01_1.mat`. License CC BY-NC 4.0; cite Lessmeier et al. 2016 | No. Damage came from lifetime tests, but only the damaged end state is recorded, not the degradation trajectory | No (classification) | [KAT]; [LESS16] |
| **MFPT** (Society for Machinery Failure Prevention Technology; Bechhoefer, NRG Systems) | NICE test-rig bearing (roller 0.235, pitch diameter 1.245, 8 elements, 0° contact angle). 3 baseline and 3 outer-race records at 270 lbs, 25 Hz shaft, 97,656 sps, 6 s. 7 outer-race and 7 inner-race records at 0/25–300 lbs, 48,828 sps, 3 s. 3 real-world faults (wind-turbine intermediate shaft bearing, oil pump bearing, planet bearing). `.mat` files with a vector of "g" data. "freely distributed" | No | No | [MFPT] |

---

## 5. Comparison

| Dataset | Institution | Bearings | Sampling rate | Samples/record | Interval | Sensors | RPM | Load | Run-to-failure | RUL usable | Primary use |
|---|---|---|---|---|---|---|---|---|---|---|---|
| IMS | U. Cincinnati IMS / Rexnord (NASA PCoE) | 3 runs × 4 bearings; 4 documented failures | 20 kHz | 20,480 (~1.02 s) | 10 min (set 1: first 43 at 5 min) | PCB 353B33 ICP accel.; 2/bearing (set 1), 1/bearing (sets 2, 3) | 2000 | 6000 lbs radial | Yes (no stated stop criterion) | Yes, limited (n=4, 1 condition) | Prognostics / degradation |
| XJTU-SY | Xi'an Jiaotong U. + Changxing Sumyoung | 15 (5 × 3 conditions) | 25.6 kHz | 32,768 (1.28 s) | 1 min | 2 × PCB 352C33 (H, V) | 2100 / 2250 / 2400 | 12 / 11 / 10 kN | Yes | Yes | RUL prognostics |
| FEMTO / PRONOSTIA | FEMTO-ST | 17 (6 learning + 11 test) | 25.6 kHz (temperature 10 Hz) | 2560 (0.1 s) | 10 s | 2 × DYTRAN 3035B (H, V) + PT100 | 1800 / 1650 / 1500 | 4000 / 4200 / 5000 N | Yes (20 g) | Yes | RUL prognostics |
| CWRU | Case Western Reserve U. | Seeded-fault DE/FE bearings | 12 kHz / 48 kHz | varies | n/a | Accelerometers DE/FE | 1797–1720 | 0–3 hp | No | No | Fault classification |
| Paderborn KAt | Paderborn U. | 32 (6 healthy / 12 artificial / 14 real) | 64 kHz | 4 s records | n/a | Vibration + motor current | 1500 / 900 | 0.7 / 0.1 Nm; 1000 / 400 N | No | No | Fault classification (MCS + vibration) |
| MFPT | MFPT / NRG Systems | Test rig + 3 field cases | 97,656 / 48,828 sps | 6 s / 3 s | n/a | Accelerometer (g) | 25 Hz shaft (1500) | 0–300 lbs | No | No | Fault diagnosis / envelope analysis |

---

## 6. Download provenance

### XJTU-SY (downloaded 2026-09-25)

- **Route:** the official MediaFire folder linked from https://biaowang.tech/xjtu-sy-bearing-datasets/
  (`http://www.mediafire.com/folder/m3sij67rizpb4/XJTU-SY_Bearing_Datasets`), subfolder `Data`
  (folderkey `0m0g59yk1pmh5`). This is an **official** route, not a mirror. It was chosen because
  MediaFire's public folder API (`/api/1.5/folder/get_content.php`) lists files with a server-side
  sha256, and its file pages give a plain HTTPS direct link, so the fetch runs non-interactively
  with curl. I did not try Google Drive, MEGA or Baidu; they were not needed. The Dropbox `/sh/`
  link returned an HTML page, not a file.
- **Throttling workaround:** one MediaFire server (download2392) served about 20–100 KB/s per
  connection, so parts 01, 02, 03 and 06 were fetched as 12 parallel HTTP Range segments
  (`xjtu/_archives/segfetch.py`, Python stdlib only) and reassembled. Every part was then checked
  against MediaFire's published sha256. All six match.
- **Extraction:** Ubuntu's `/usr/bin/7z` (p7zip 23.01) lacks the RAR decoder ("Unsupported Method" on
  every file). I used the official 7-Zip 23.01 Linux build from 7-zip.org
  (`https://www.7-zip.org/a/7z2301-linux-x64.tar.xz`, sha256 `23babcab…4cbcf318`), unpacked
  user-locally in `~/work/external_data/_tools/7zz/`. Nothing was installed system-wide.
  Result: 9,217 files, 19 folders, 12,220,812,451 bytes, exit code 0. The only warning was the
  benign "There are data after the end of archive" (6,783-byte tail on part01).
- **Local path:** `~/work/external_data/xjtu/XJTU-SY_Bearing_Datasets/`. Archives are kept in
  `~/work/external_data/xjtu/_archives/`.

| Archive | Bytes | sha256 (local = MediaFire) |
|---|---|---|
| XJTU-SY_Bearing_Datasets.part01.rar | 744,488,960 | c500657353f089a4ab50212ff4ddfc7b982729e92e2b127440c8ad881d80b968 |
| XJTU-SY_Bearing_Datasets.part02.rar | 744,488,960 | 4dfa6286a8e9c7cec1e925b347642349f36e27ab3f703c90d1d08977b7b4f61f |
| XJTU-SY_Bearing_Datasets.part03.rar | 744,488,960 | 6929f531284f79e0209246b4ee23b23dd8d4faac1c0c3ff8fb131cda4a18bd3a |
| XJTU-SY_Bearing_Datasets.part04.rar | 744,488,960 | 2245825acd29bed3b95e7a77879a3fbadf20f4ad4f99486384c714174621597d |
| XJTU-SY_Bearing_Datasets.part05.rar | 744,488,960 | e1b0a41a32b865e48ea7981c56f952a960d94335f3496b72eb4a65932f1671bd |
| XJTU-SY_Bearing_Datasets.part06.rar | 722,155,640 | df1854821a9d481104476379f7bc045ea1e101427c6e36145cd7677dc7c4a684 |

Observed tree. CSV counts match tutorial Table 3 exactly, files are numbered contiguously
`1.csv … N.csv`, and every final file has a header plus 32,768 rows:

```
XJTU-SY_Bearing_Datasets/
├── Introduction_to_XJTU-SY_Bearing_Dataset.pdf
├── 35Hz12kN/    Bearing1_1 (123)  Bearing1_2 (161)  Bearing1_3 (158)  Bearing1_4 (122)  Bearing1_5 (52)
├── 37.5Hz11kN/  Bearing2_1 (491)  Bearing2_2 (161)  Bearing2_3 (533)  Bearing2_4 (42)   Bearing2_5 (339)
└── 40Hz10kN/    Bearing3_1 (2538) Bearing3_2 (2496) Bearing3_3 (371)  Bearing3_4 (1515) Bearing3_5 (114)
```

First 3 lines of `35Hz12kN/Bearing1_1/1.csv` (CRLF line endings; 32,769 lines total):
```
Horizontal_vibration_signals,Vertical_vibration_signals
-0.39639469236135483,-0.03867150051519275
-0.12310739606618881,-0.36590099334716797
```

Supporting documents from the same official MediaFire folder (`xjtu/_docs/`):

| File | Bytes | sha256 |
|---|---|---|
| ReadMe.txt | 817 | c5430c7d6fc2ca71b219e94f395bb2d2ef079bed912a19c81110ccac06123278 |
| Download_Links_20190306.txt | 657 | 097744e20c02216d5bc05e62659cbab74e37829187dffcd8c87dd1cdaa2d8cec |
| Wang2020_hybrid_prognostics.pdf | 4,720,469 | 65ce6e2ddaf11ca22ecbd1f7c4fda2d47cfb69078dbdcbccdb3525a98d500fcd |
| XJTU-SY_interpretation_zh.pdf | 590,816 | c5f36069babef7415f41b05dc3755c645f5a4f21734947c606329c648420bed8 |

### Reference documents (`~/work/external_data/_refs/`, fetched 2026-09-25)

| File | URL | Bytes | sha256 |
|---|---|---|---|
| IMS_Readme.pdf | archive.org/download/NASA_PCoE_Bearing_Documentation/Readme Document for IMS Bearing Data.pdf | 400,443 | cf46d37c21f7f292c11bbbdd4695d876c417ed1d6425e3d87c962ae2182ae6ed |
| IEEEPHM2012-Challenge-Details.pdf | raw.githubusercontent.com/wkzs111/phm-ieee-2012-data-challenge-dataset/master/… (GitHub re-host of the FEMTO-ST document) | 2,279,692 | 13bd43eb2dc4c8455e36584094552ccbd8101b9a0b99bd10ca82103453585ba5 |
| Lessmeier2016_PHME.pdf | papers.phmsociety.org/index.php/phme/article/download/1577/542 | 1,655,352 | c1f75c79cfbcbcbfd24b32bf034cebb76d1c3ff7864827575d37387bb0955f84 |

### CWRU (downloaded 2026-10-07)

Official source: Case Western Reserve University Bearing Data Center,
`https://engineering.case.edu/bearingdatacenter/download-data-file`. Individual files
are served at `https://engineering.case.edu/sites/default/files/<id>.mat` (confirmed by
HTTP HEAD, 200 OK, `Content-Length` matching the downloaded file size).

**Classification: FAULT_DIAGNOSIS / CONDITION_MONITORING, NOT run-to-failure.** Each file
is a single short recording at one fixed fault condition and load - there is no elapsed-time
axis and no degradation trajectory, so no RUL ground truth exists for this dataset. This
project never reports an RUL metric for CWRU (see `ml-data.md`).

Format: MATLAB v5 `.mat` files. Each carries 2-4 variables named `X<id>_<channel>_time`
(DE = drive end accelerometer, FE = fan end, BA = base; `channel` is what the published
literature centers fault-diagnosis features on) plus an `X<id>RPM` scalar when recorded.
**Variable-name zero-padding is inconsistent across the archive** - file 97 stores its
variable as `X097_DE_time` (zero-padded), while e.g. 105 stores `X105_DE_time` (not
padded); `cwru.py`'s `_find_time_variable` resolves by channel suffix rather than
assuming either convention.

`scipy.io.loadmat` cannot read every variable of some of these files in a single call
(`OSError: could not read bytes` on a later variable) - confirmed not to be a download
problem (`scipy.io.whosmat` lists all variables correctly, and reading any one named
variable alone succeeds for every file tested). `cwru.py` always reads one named variable
per call.

4 files downloaded (12 kHz drive-end set, 0.007" fault diameter, 0 HP load) for adapter
development/tests - not the full archive (hundreds of files across fault diameters,
loads, and sampling rates):

| file | label | bytes | sha256 |
|---|---|---|---|
| 97.mat | normal baseline | 1,965,609 | 6abd6f41c69ab2a46f6bc5f73b325d3ddd4c2c336e9ee9f2468b0aec7dcda4cc |
| 105.mat | inner race fault, 0.007in | 2,910,768 | f80b0ea04fd06b372a0eaec7c056543ea37e4bb4727a5b173d2a5bacd2aa9cab |
| 118.mat | ball fault, 0.007in | 2,942,112 | b00628f8dd8d1d930af77fa465d1e5cdb385fe259489053f91f3680bda7f640e |
| 130.mat | outer race fault @6:00, 0.007in | 2,928,192 | 35a095307d0971477049b343a1b5981dde465a58fb7f233ad89b035068c1717d |

Raw files kept outside both repo clones at `/mnt/NewVolume/capstone/data/CWRU_12k_DE/`
(same convention as the other external raw-data downloads documented in the capstone-root
`CLAUDE.md`). Small excerpts (first 12,000 samples = 1s at 12kHz of the DE channel only)
are committed as test fixtures at `data/fixtures/cwru/*.mat`.

Real applicability check against the frozen FEMTO `cross_domain_bundle.joblib`
(`tests/test_cwru.py::test_cwru_applicability_against_frozen_femto_model`, run
2026-10-07): **level = LOW** - every `vibration_y_*` column reported missing (CWRU has
only one accelerometer axis per recording, FEMTO's model expects two), plus a genuine
feature-distribution shift (median kNN distance 2.62 vs in-domain 1.36, shift_ratio
1.92x). This is the scientifically correct outcome, not a failure: CWRU is a dataset type
the FEMTO model was never fit on, and the applicability layer correctly flags it rather
than scoring it as if in-domain.

### IMS (downloaded 2026-09-25)

Official NASA route `https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip`, downloaded with
curl (exit 0, 1,075,597,174 bytes = Content-Length), sha256 in `ims/bearings.zip.sha256`; extracted
with the official 7-Zip 23.01 build (the distribution `7z` cannot decode RAR). The official NASA zip is 1,075,597,174 bytes (HTTP HEAD, 2026-09-25; S3 ETag
`a201e36fe558f3f50509701b6d573532-63`, a multipart ETag, not an md5).
