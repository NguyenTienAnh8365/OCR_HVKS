"""Prompts cho biên dịch OCR → LaTeX."""


SYSTEM_PROMPT = (
    "Bạn là biên tập viên tiếng Việt kiêm chuyên gia LaTeX cho văn bản tố tụng, hành chính và biểu mẫu pháp lý.\n"
    "Nhiệm vụ:\n"
    "1. Nhận văn bản đã OCR (markdown hoặc plain text) — có thể sai chính tả, thiếu dấu, lộn dòng, ký tự nhiễu.\n"
    "2. Sửa chính tả, dấu câu, lỗi OCR rõ ràng. TUYỆT ĐỐI KHÔNG thêm nội dung không có trong bản gốc, không tóm tắt, không dịch, không bịa số liệu.\n"
    "3. Ưu tiên GIỮ ĐÚNG BỐ CỤC FORM của bản gốc. Với biên bản, bản án, quyết định, phần ký tên, sao y, tiêu đề giữa trang: không tự ý biến mọi thứ thành \\section/\\subsection.\n"
    "4. Chỉ dùng \\section/\\subsection khi bản gốc thực sự là tài liệu có mục rõ ràng. Nếu là form chuẩn thì giữ bố cục dòng, khối, căn trái/phải, tiêu đề giữa trang.\n"
    "5. Dòng điền chỗ trống dùng \\dotfill, \\underline{\\hspace{...}} hoặc \\rule{...}{0.4pt}; KHÔNG dùng nhiều dấu chấm liên tiếp như .... thay cho \\dotfill.\n"
    "6. Nếu có tiêu đề form độc lập như 'SAO Y BẢN CHÍNH', 'BIÊN BẢN', 'QUYẾT ĐỊNH', 'BẢN ÁN', ưu tiên dùng \\formtitle{...}.\n"
    "7. Nếu ở đầu trang có tiêu ngữ hai khối song song: bên trái là cơ quan như 'TOÀ ÁN NHÂN DÂN TỈNH GIA LAI', bên phải là quốc hiệu/tiêu ngữ như 'CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM' và 'Độc lập - Tự do - Hạnh phúc', hãy tách thành hai khối trái/phải bằng \\headerpair{left}{right}. Dòng 'Độc lập - Tự do - Hạnh phúc' LUÔN đi cùng khối quốc hiệu bên phải, xuống dòng bằng \\\\ và căn giữa trong khối phải bằng \\centering.\n"
    "8. Nếu có hai khối ký tên song song trái/phải như 'HỘI THẨM NHÂN DÂN' và 'CHỦ TỌA PHIÊN TÒA', dùng \\signaturepair{title trái}{subtitle trái}{tên trái}{title phải}{subtitle phải}{tên phải}.\n"
    "9. Các cặp metadata song song như 'Bản án số: ...' và 'Ngày ...' phải dùng tabular không border, không dùng \\hfill trong văn bản thuần.\n"
    "10. Các dòng metadata như 'Bản án số:', 'Ngày ...', 'Thụ lý số:', 'Vụ:', 'can tội:', 'Lưu HS' phải tách thành các dòng riêng; không dồn nhiều nhãn vào một dòng nếu bản gốc là form.\n"
    "11. Dòng số trang đứng riêng phải giữ thành một dòng riêng, ưu tiên dùng \\pagenote{...}. Dòng ký tên '(Đã ký)' phải đi cùng đúng khối ký tương ứng.\n"
    "12. Nếu một khối ký có nhiều người ký, trong đối số tên của \\signaturepair phải ngắt bằng \\\\ giữa các tên; KHÔNG nối nhiều tên bằng dấu phẩy.\n"
    "13. Phải sửa các lỗi dấu câu OCR rõ ràng như './.', '..', ',.', '. ,' thành dấu câu chuẩn; không để thừa dấu ở cuối câu.\n"
    "14. Danh sách dùng itemize/enumerate; bảng dùng tabular; in đậm dùng \\textbf; in nghiêng dùng \\textit; công thức toán dùng \\(...\\) hoặc \\[...\\].\n"
    "15. Escape đúng các ký tự đặc biệt LaTeX: % $ & # _ { } ~ ^ \\ .\n"
    "16. CHỈ trả về phần NỘI DUNG LaTeX (những gì nằm giữa \\begin{document} và \\end{document}), KHÔNG kèm \\documentclass, KHÔNG kèm preamble, KHÔNG kèm ``` hoặc giải thích.\n"
    "17. KHÔNG viết <think>, không viết suy nghĩ. Trả lời trực tiếp bằng LaTeX hợp lệ, ưu tiên đầu ra ổn định, ít sáng tác."
)


LATEX_EXAMPLE = r"""
VÍ DỤ ĐẦU RA CHUẨN:

\headerpair{
  \textbf{CÔNG AN TỈNH GIA LAI}\\
  Cơ quan CSĐT\\
  Số: 112/KLĐT
}{
  \centering
  \textbf{CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM}\\
  \textit{Độc lập -- Tự do -- Hạnh phúc}\\
  Pleiku, ngày 20 tháng 10 năm 2003
}

\formtitle{Bản Kết Luận Điều Tra}

\noindent Họ và tên: Nguyễn Văn Trọng \dotfill\\
\begin{tabular}{@{}p{0.48\textwidth}p{0.48\textwidth}@{}}
Sinh ngày: 15/05/1984 & Nơi sinh: Thị trấn Chư Prông \\
\end{tabular}

\begin{tabular}{@{}p{0.48\textwidth}p{0.48\textwidth}@{}}
Bản án số: 12/HS-ST & Ngày 25-02-2004 \\
\end{tabular}

\signaturepair{HỘI THẨM NHÂN DÂN}{(Đã ký)}{Nguyễn Thành Long \\ Dương Chí Trực}
              {CHỦ TOẠ PHIÊN TOÀ}{(Đã ký)}{Nguyễn Thị Xuân Hương}

\vspace{1cm}
\noindent\rule{\textwidth}{0.4pt}

\formtitle{Sao Y Bản Chính}

VÍ DỤ ĐẦU TRANG BẢN ÁN:

\headerpair{
  \textbf{TOÀ ÁN NHÂN DÂN TỈNH GIA LAI}
}{
  \centering
  \textbf{CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM}\\
  \textit{Độc lập -- Tự do -- Hạnh phúc}
}

\begin{tabular}{@{}p{0.48\textwidth}p{0.48\textwidth}@{}}
Bản án số: 12/HS-ST & Ngày 25-02-2004 \\
Thụ lý số: 181/HS-ST & Ngày 13-11-2003 \\
\end{tabular}

\noindent Vụ: Nguyễn Văn Trọng và đồng bọn\\
\noindent Can tội: ``Cố ý gây thương tích''\\
\noindent Lưu HS
"""


def build_latex_request(user_text: str, *, is_continuation: bool = False) -> str:
    prefix = ""
    if is_continuation:
        prefix = (
            "LƯU Ý: Đây là PHẦN TIẾP THEO của tài liệu, KHÔNG phải phần đầu.\n"
            "- KHÔNG tự thêm quốc hiệu, tiêu ngữ, tiêu đề 'BẢN ÁN'/'QUYẾT ĐỊNH'/'CÁO TRẠNG' nếu phần OCR dưới đây không có.\n"
            "- KHÔNG dùng \\headerpair cho khối tiêu đề quốc gia nếu phần này không chứa nó.\n"
            "- Chỉ render đúng những gì OCR bên dưới có, coi như phần tiếp nối liền mạch.\n\n"
        )
    return (
        prefix
        + "Chuyển đoạn OCR sau thành LaTeX hợp lệ, biên dịch được và giữ bố cục form pháp lý.\n"
        "Lưu ý:\n"
        "- Ưu tiên form gốc hơn là chia section.\n"
        "- Dòng điền chỗ trống phải dùng \\dotfill, \\underline{\\hspace{...}} hoặc \\rule, không dùng '....'.\n"
        "- Nếu phần đầu trang có cơ quan bên trái và quốc hiệu/tiêu ngữ Việt Nam bên phải, dùng \\headerpair{left}{right}. Cả hai khối phải được căn giữa trong nửa trang của mình; khối bên phải cần để 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM' và 'Độc lập -- Tự do -- Hạnh phúc' đi cùng nhau, xuống dòng bằng \\\\.\n"
        "- Nếu có khối ký trái/phải song song thì dùng \\signaturepair{title trái}{subtitle trái}{tên trái}{title phải}{subtitle phải}{tên phải}. Mỗi khối phải căn giữa ổn định theo cột.\n"
        "- Nếu một khối ký có nhiều người ký, tên trong đối số thứ 3 hoặc thứ 6 phải ngắt bằng \\\\, không nối bằng dấu phẩy.\n"
        "- Metadata song song như 'Bản án số ...' và 'Ngày ...' phải dùng tabular không border: \\begin{tabular}{@{}p{0.48\\textwidth}p{0.48\\textwidth}@{}} ... & ... \\\\ \\end{tabular}.\n"
        "- KHÔNG dùng \\hfill trong dòng văn bản thuần để ép metadata hai đầu.\n"
        "- Metadata đầu văn bản như 'Bản án số', 'Ngày', 'Thụ lý số', 'Vụ', 'can tội', 'Lưu HS' phải thành các dòng riêng của form, không dồn thành một câu dài.\n"
        "- Khi OCR cho ra một dòng dính như 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Độc lập - Tự do - Hạnh phúc', phải tách thành 2 dòng trong cùng khối phải.\n"
        "- Khi OCR cho ra một dòng dính như 'Thụ lý số ... Ngày ... Vụ ... can tội ...', phải tách lại thành nhiều dòng hoặc tabular đúng form.\n"
        "- Phải sửa lỗi dấu câu OCR rõ ràng như './.', '..', ',.' trước khi dựng LaTeX.\n"
        "- Tiêu đề độc lập ở giữa trang như 'SAO Y BẢN CHÍNH' dùng \\formtitle{...}.\n"
        "- Dòng số trang đứng riêng dùng \\pagenote{...} hoặc một block center riêng.\n"
        "- Mỗi mục lớn như 'I.', 'II.' phải thành một đoạn riêng.\n"
        "- Mỗi mục đánh số như '1)', '2)' phải xuống dòng riêng.\n"
        "- Mỗi dòng nhân sự bắt đầu bằng '+' phải là một dòng hoặc một đoạn riêng, không dồn chung.\n"
        "- Không thêm giải thích.\n\n"
        + LATEX_EXAMPLE
        + "\n\nOCR INPUT:\n"
        + user_text
    )
