# MV technique catalogue

Use this to PROPOSE techniques from the song's meaning (see SKILL.md step 3). Every proposal = technique ID +
one line tying it to the lyric/emotion. ✅ = `mv.py` renders it · 🛠 = manual in CapCut/Resolve or extend `mv.py`.

House style: **soft seams by default** - splits use `feather` 0.2 (set `feather: 0` only when a hard,
graphic contrast is the point, e.g. "anh / em", before / after, beat-heavy dance break).

## 1. Composition - putting 2+ videos in one frame
| ID | Tên | Ý nghĩa / khi dùng | storyboard | |
|---|---|---|---|---|
| C-SPLIT-SOFT | Chia đôi viền mềm | Hai thế giới / hai thời điểm tan vào nhau: hoài niệm, nhớ nhung, "ở hai nơi" | `layout: split_v` (feather 0.2 mặc định), nửa ký ức `fx: [blur:10, warm]` | ✅ |
| C-SPLIT-HARD | Chia đôi cắt cứng | Đối lập rõ ràng, nhịp mạnh, so sánh | `split_v` + `feather: 0` | ✅ |
| C-SIDE | Chia trái/phải | Hai người đối diện, đối thoại, khoảng cách | `split_h` (+ `mirror` cho một bên) | ✅ |
| C-TRIPTYCH | Ba tầng | Điệp khúc cuối: tổng hợp mọi tuyến hình | `split_3v` | ✅ |
| C-PIP | Khung trong khung | Hiện tại "nhìn lại" quá khứ, reaction | `pip`, `inset.pos` | ✅ |
| C-DOUBLE-EXPO | Chồng mờ (double exposure) | Ký ức đè lên hiện tại, nhớ một người, nỗi nhớ ám ảnh | lớp 2 `blend: screen, opacity: 0.35-0.5, fx: [blur:6-10]` | ✅ |
| C-DREAM-MIX | Hoà 50/50 + glow | Mơ, hồi tưởng, lâng lâng | lớp 2 `blend: normal, opacity: 0.5`, shot `fx: [glow]` | ✅ |
| C-SOFTLIGHT | Phủ ảnh kỷ niệm | Ảnh cũ / kỷ vật thấm vào cảnh | `blend: softlight, opacity: 0.4`, ảnh + `zoom: in` | ✅ |
| C-FIT-BLUR | Khung ngang trên nền blur | Giữ nguyên khung sân khấu/live 16:9 trong video dọc | `layout: fit_blur` | ✅ |
| C-LIGHT-LEAK | Light leak / film burn | Ấm áp, ký ức đẹp, chuyển đoạn | clip light-leak stock làm lớp `blend: screen` 0.5-0.8 | ✅ (cần clip) |

## 2. Rhythm - sync with the music
| ID | Tên | Ý nghĩa / khi dùng | storyboard | |
|---|---|---|---|---|
| R-BEAT-CUT | Cắt đúng beat | Nền tảng của mọi MV | cut tại `analysis.json` beats/downbeats | ✅ |
| R-ACCEL | Dồn nhịp | Pre-chorus: shot ngắn dần 4→2→1 beat, tạo căng | độ dài shot giảm dần | ✅ |
| R-FLASH-DROP | Flash trên drop | Bùng nổ khi vào điệp khúc | `transition: flash` | ✅ |
| R-ZOOM-PULSE | Zoom nảy theo beat | Điệp khúc sôi động, dance, fan cổ vũ | `beat_fx: [zoom]`, `beat_every: 1|2` | ✅ |
| R-BEAT-FLASH | Nháy sáng theo beat | Ánh đèn sân khấu, lightstick, phấn khích | `beat_fx: [flash]` | ✅ |
| R-SHAKE | Rung khung theo trống | Cao trào, gào thét, cảm xúc vỡ oà | `beat_fx: [shake]` (nhẹ tay, ≤ 2-4s) | ✅ |
| R-SLOWMO | Slow motion | Khoảnh khắc ngưng đọng, bridge, câu đắt nhất | `speed: 0.5` (nguồn 50/60fps đẹp hơn) | ✅ |
| R-SPEED-RAMP | Tăng tốc → chậm | Chuyển đoạn "vút" rồi dừng vào câu hát | | 🛠 |
| R-FREEZE | Dừng hình + chữ | Nhấn mạnh 1 câu / 1 ánh mắt | | 🛠 |

## 3. Transitions
| ID | Tên | Ý nghĩa | storyboard | |
|---|---|---|---|---|
| X-DISSOLVE | Hoà tan | Thời gian trôi, nhẹ nhàng, ký ức | `dissolve:0.6` | ✅ |
| X-DIP-BLACK | Tối dần | Khép một chương, im lặng trước bridge | `fadeblack:0.8` | ✅ |
| X-DIP-WHITE | Trắng loá | Bừng tỉnh, quay về quá khứ, thiên đường | `fadewhite:0.5` / `flash` | ✅ |
| X-CIRCLE | Mở tròn | "Mở cửa", mở ra thế giới mới | `circleopen:0.5` | ✅ |
| X-BLUR | Nhoè chuyển | Mơ màng, say, chóng mặt | `hblur:0.4` | ✅ |
| X-SLIDE | Trượt / wipe | Năng lượng, vui, dance | `slideup:0.3`, `wipeleft:0.3` | ✅ |
| X-WHIP | Whip pan | Đổi không gian cực nhanh | gần đúng `smoothleft:0.2`; chuẩn 🛠 | ✅/🛠 |
| X-MATCH-CUT | Match cut | Khớp hình/chuyển động giữa 2 cảnh (tay đẩy cửa → cửa mở ở thời khác) - "chất điện ảnh" | chọn `in:` bằng `mv sheet`, `cut` | ✅ |

## 4. Look / color
| ID | Look | Cảm xúc | fx |
|---|---|---|---|
| L-WARM-FILM | Phim ấm | Hoài niệm đẹp, tuổi trẻ | `vintage`, `grain:8`, `warm` |
| L-OLDFILM | Phim cũ bạc màu | Quá khứ xa, mất mát | `oldfilm` |
| L-VHS | Băng VHS | 90s, kỷ niệm gia đình, retro | `vhs` |
| L-BW | Đen trắng | Cô đơn, sự thật trần trụi, bridge | `bw`, `contrast:1.15` |
| L-COOL | Lạnh | Chia ly, đêm, mưa | `cool`, `sat:0.85` |
| L-GLOW | Toả sáng | Sân khấu, lightstick, mơ | `glow` |
| L-GLITCH | Glitch | Rối loạn, giằng xé, beat điện tử | `rgbsplit`, `vhs` (ngắn) |

## 5. Lyrics / text  (full guide: `reference/lyrics.md`)
| ID | Kiểu | Khi dùng | storyboard |
|---|---|---|---|
| K-FADE | Hiện mờ | Verse, ballad | `lyric_style: subtitle` (fade) |
| K-RISE | Trôi lên | Câu nhẹ nhàng, tự sự | `subtitle` + `lyric_anim: rise` |
| K-POP | Bật nảy | Hook, câu catchy | `subtitle` + `lyric_anim: pop` |
| K-KARAOKE | Tô màu từng chữ theo giọng hát | Singalong, fan edit, điệp khúc | `lyric_style: karaoke` |
| K-WORD | Hiện từng chữ | Rap, câu chậm nhiều cảm xúc | `lyric_style: word` |
| K-TYPE | Đánh máy | Tâm sự, thư, tin nhắn, intro | `lyric_style: typewriter` |
| K-STACK | Chữ lớn xếp tầng (kinetic) | Hook/drop, video lyric viral | `lyric_style: stack` |
| K-NEON | Neon phát sáng | Đêm, EDM, retro, tình yêu về đêm | `lyric_style: neon` |
| K-SCROLL | Danh sách cuộn kiểu Apple Music | Lyric video, poster player | `lyric_style: scroll` |
| K-BILINGUAL | Song ngữ | Bài quốc tế, fan nước ngoài | `câu | translation` trong lyrics.txt |
| K-POSTER | Poster player (bìa + lyric + thanh tiến trình) | Chỉ có poster/cover, video lyric nhanh | `layout: poster` |
| K-TITLE | Tiêu đề giữa khung | Mở/kết, tên bài | `caption_style: title` |

## 6. Storytelling devices (concept level)
| ID | Thủ pháp | Mô tả |
|---|---|---|
| S-MOTIF | Hình ảnh lặp | Một vật/hình xuất hiện ở đầu và cuối (cánh cửa, chiếc đàn) → câu chuyện khép vòng |
| S-THEN-NOW | Xưa - nay | Cùng người/nơi/bài hát ở hai thời điểm; ghép bằng C-SPLIT-SOFT hoặc C-PIP |
| S-CALLBACK | Gọi lại | Điệp khúc cuối lướt nhanh lại các shot đã thấy (R-ACCEL) |
| S-CALL-RESPONSE | Hát - đáp | Ca sĩ hát câu → cắt sang fan hát theo / vẫy lightstick |
| S-LITERAL-METAPHOR | Minh hoạ vs ẩn dụ | Không minh hoạ sát từng chữ; xen 1 câu literal với 2-3 câu ẩn dụ |
| S-HOOK-3S | Móc câu 3 giây | Shot đầu tiên mạnh nhất (cảnh đẹp nhất / câu hook) để giữ người xem trên TikTok |

## Mood → quick picks
| Bài / đoạn mang ý | Gợi ý nhanh |
|---|---|
| Hoài niệm, nhớ về | C-SPLIT-SOFT + L-WARM-FILM + X-DISSOLVE + C-DOUBLE-EXPO |
| Chia ly, buồn | L-COOL/L-BW + R-SLOWMO + X-DIP-BLACK + K-RISE |
| Tình yêu ngọt | L-GLOW + C-DREAM-MIX + X-DIP-WHITE + K-FADE |
| Sôi động, dance, quẩy | R-BEAT-CUT + R-ZOOM-PULSE + R-BEAT-FLASH + X-SLIDE + K-POP |
| Cao trào, vỡ oà | R-ACCEL → R-FLASH-DROP + R-SHAKE (ngắn) + C-TRIPTYCH |
| Tri ân fan / concert | S-CALL-RESPONSE + C-SPLIT-SOFT (ca sĩ / fan) + L-GLOW + R-BEAT-FLASH |
| Kể chuyện, hành trình | S-MOTIF + X-MATCH-CUT + X-CIRCLE + S-THEN-NOW |

## Rules of thumb
- Cut on the beat; big changes on downbeats/section starts; never cut mid-word.
- Average shot: verse 2.5-4s, chorus 0.8-2s; vary it.
- Max 2-3 layers at once; overlays 25-50% opacity.
- One signature look per section; save the strongest effect (shake, flash burst) for 1-2 moments.
- Keep faces/text out of the bottom ~20% and right ~12% in 9:16 (platform UI).

## Platform specs
| Platform | Aspect / size | Notes |
|---|---|---|
| TikTok, Reels, Shorts, FB Reels | 9:16 1080x1920, 30fps | hook in first 1-3s; Shorts <= 3 min |
| YouTube | 16:9 1920x1080 / 3840x2160 | full song, lower-third lyrics |
| Facebook feed | 4:5 1080x1350 or 1:1 | |
