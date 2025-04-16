import streamlit as st
import openai
import os
import json
import base64
from PIL import Image, ImageDraw, ImageFont
from ebooklib import epub
import io
import zipfile
import hashlib

# ------------------ Integração com Google Drive ------------------
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Caminho da logo
LOGO_PATH = "Terra_Cultural_sem_fundo.png"

def upload_to_drive(file_bytes, filename, folder_id=None):
    SCOPES = ['https://www.googleapis.com/auth/drive']
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json is None:
        st.error("A variável de ambiente (ou secret) GOOGLE_SERVICE_ACCOUNT_JSON não está definida!")
        return None

    service_account_info = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)
    
    file_metadata = {
        'name': filename,
        'mimeType': 'application/zip'
    }
    if folder_id:
        file_metadata['parents'] = [folder_id]
    
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='application/zip')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

openai.api_key = os.getenv("OPENAI_API_KEY")

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    else:
        return ""

def int_to_roman(num):
    val = [1000, 900, 500, 400,
           100, 90, 50, 40,
           10, 9, 5, 4,
           1]
    syms = ["M", "CM", "D", "CD",
            "C", "XC", "L", "XL",
            "X", "IX", "V", "IV",
            "I"]
    roman_num = ''
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            roman_num += syms[i]
            num -= val[i]
        i += 1
    return roman_num

def add_page_number(image, display_number, alignment, style="Padrão", custom_color=None):
    img = image.copy()
    draw = ImageDraw.Draw(img)
    
    # Utiliza uma altura padrão (ex.: altura de exportação do PDF com sangria)
    default_height = 2775  # pixels
    font_size = int(default_height / 45)  # ajuste esse divisor conforme necessário

    # Seleciona a fonte conforme o estilo
    if style == "Romano":
        font_path = os.path.join("fonts", "EBGaramond-Regular.ttf")
    elif style == "Fresco":
        font_path = os.path.join("fonts", "Pacifico-Regular.ttf")
    elif style == "Moderno":
        font_path = os.path.join("fonts", "Montserrat-Regular.ttf")
    elif style == "Elegante":
        font_path = os.path.join("fonts", "CormorantGaramond-Regular.ttf")
    elif style == "Desenhado":
        font_path = os.path.join("fonts", "ButterflyKids-Regular.ttf")
    else:
        font_path = os.path.join("fonts", "Roboto-Regular.ttf")
    
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        font = ImageFont.load_default()

    text = int_to_roman(display_number) if style == "Romano" else str(display_number)

    # Define cores e contornos (outline) conforme o estilo
    if style in ["Padrão", "Romano"]:
        fill_color = custom_color if custom_color else "#FFFFFF"
        outline_range = 1
        do_outline = True
    elif style == "Fresco":
        fill_color = custom_color if custom_color else "#FFD700"
        outline_range = 2
        do_outline = True
    elif style == "Moderno":
        fill_color = custom_color if custom_color else "#007BFF"
        outline_range = 0
        do_outline = False
    elif style == "Elegante":
        fill_color = custom_color if custom_color else "#8E44AD"
        outline_range = 1
        do_outline = True
    elif style == "Desenhado":
        fill_color = custom_color if custom_color else "#FF69B4"
        outline_range = 1
        do_outline = True
    else:
        fill_color = custom_color if custom_color else "#FFFFFF"
        outline_range = 1
        do_outline = True

    # Posicionamento com base na largura real da imagem
    width, height = img.size
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    margin = int(2 / 2.54 * 96)  # 2 cm em pixels

    if alignment == "Esquerda":
        x = margin
    elif alignment == "Direita":
        x = width - text_width - margin
    else:
        available_width = width - 2 * margin
        x = margin + (available_width - text_width) / 2

    y = height - text_height - margin

    if do_outline and outline_range > 0:
        for dx in range(-outline_range, outline_range + 1):
            for dy in range(-outline_range, outline_range + 1):
                draw.text((x + dx, y + dy), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill=fill_color)
    return img

def add_logo_bottom_center(image, logo_path=LOGO_PATH, margin_bottom_cm=1.0, max_logo_width=200):
    if not os.path.exists(logo_path):
        return image 
    img = image.copy()
    logo = Image.open(logo_path)

    ratio = max_logo_width / logo.width
    new_w = int(logo.width * ratio * 0.5)
    new_h = int(logo.height * ratio * 0.5)
    logo = logo.resize((new_w, new_h), Image.LANCZOS)

    if logo.mode != "RGBA":
        logo = logo.convert("RGBA")

    margin_px = int(margin_bottom_cm / 2.54 * 96)
    x = (img.width - new_w) // 2
    y = img.height - margin_px - new_h

    if img.mode == "RGBA":
        img.alpha_composite(logo, (x, y))
    else:
        img.paste(logo, (x, y), logo)
    return img

def generate_pdf(images):
    pdf_bytes = io.BytesIO()
    if images:
        images[0].save(pdf_bytes, format="PDF", save_all=True, append_images=images[1:])
    pdf_bytes.seek(0)
    return pdf_bytes

def scale_and_crop_to_fill(img, target_w, target_h):
    w, h = img.size
    ratio_img = w / h
    ratio_target = target_w / target_h

    if ratio_img > ratio_target:
        new_height = target_h
        scale = new_height / h
        new_width = int(w * scale)
        resized = img.resize((new_width, new_height), resample=Image.LANCZOS)
        left = (new_width - target_w) // 2
        final_img = resized.crop((left, 0, left + target_w, new_height))
    else:
        new_width = target_w
        scale = new_width / w
        new_height = int(h * scale)
        resized = img.resize((new_width, new_height), resample=Image.LANCZOS)
        top = (new_height - target_h) // 2
        final_img = resized.crop((0, top, new_width, top + target_h))
    return final_img

def generate_pdf_sangria(images, dpi=300):
    width_inch = 6.125
    height_inch = 9.25
    target_w = int(round(width_inch * dpi))   # ~1838 px
    target_h = int(round(height_inch * dpi))    # ~2775 px

    pdf_pages = []
    for img in images:
        if img.mode != "RGB":
            img = img.convert("RGB")
        filled_img = scale_and_crop_to_fill(img, target_w, target_h)
        pdf_pages.append(filled_img)

    pdf_bytes = io.BytesIO()
    if pdf_pages:
        pdf_pages[0].save(pdf_bytes, format="PDF", resolution=dpi, save_all=True, append_images=pdf_pages[1:])
    pdf_bytes.seek(0)
    return pdf_bytes

def generate_epub(files, start_page, end_page, initial_number, alignment, number_style, custom_color=None, add_numbering=True):
    book = epub.EpubBook()
    book.set_identifier("id_livro_123")
    book.set_title("Livro Ilustrado")
    book.set_language("pt")
    book.add_author("Globaltec")
    
    html_colors = {
        "Padrão": custom_color if custom_color else "#FFFFFF",
        "Romano": custom_color if custom_color else "#FFFFFF",
        "Fresco": custom_color if custom_color else "#FFD700",
        "Moderno": custom_color if custom_color else "#007BFF",
        "Elegante": custom_color if custom_color else "#8E44AD"
    }
    
    chapters = []
    for idx, f_dict in enumerate(files):
        page_position = idx + 1
        image_data = f_dict["data"]
        image_filename = f"image_{idx}.jpg"
    
        epub_img = epub.EpubItem(
            uid=image_filename,
            file_name=image_filename,
            media_type="image/jpeg",
            content=image_data
        )
        book.add_item(epub_img)
    
        if add_numbering and start_page <= page_position <= end_page:
            display_number = initial_number + (page_position - start_page)
            display_text = int_to_roman(display_number) if number_style == "Romano" else str(display_number)
            html_color = html_colors.get(number_style, "#FFFFFF")
            if alignment == "Esquerda":
                align_style = "text-align:left; margin-left:75px;"
            elif alignment == "Direita":
                align_style = "text-align:right; margin-right:75px;"
            else:
                align_style = "text-align:center; margin:0 75px;"
            number_html = f"<div style='{align_style} font-size:16px; margin-top:10px; color:{html_color};'>{display_text}</div>"
        else:
            number_html = ""
    
        c = epub.EpubHtml(
            title=f"Página {page_position}",
            file_name=f"page_{idx}.xhtml",
            lang="pt"
        )
        c.content = f"""
        <html>
          <head>
            <meta charset="utf-8" />
            <title>Página {page_position}</title>
          </head>
          <body>
            <h1>Página {page_position}</h1>
            <img src="{image_filename}" alt="Página {page_position}" style="width:100%;"/>
            {number_html}
          </body>
        </html>
        """
        book.add_item(c)
        chapters.append(c)
    
    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters
    
    epub_bytes = io.BytesIO()
    epub.write_epub(epub_bytes, book)
    epub_bytes.seek(0)
    return epub_bytes

def move_page(file_index, new_position):
    order = st.session_state.order
    current_pos = order.index(file_index)
    order.pop(current_pos)
    new_index = max(0, min(new_position - 1, len(order)))
    order.insert(new_index, file_index)
    st.session_state.order = order
    st.rerun()

# Atualização da remoção: a ordenação é ajustada sem reinicializar para preservar a configuração
def remove_page(file_index):
    st.session_state.file_data.pop(file_index)
    new_order = []
    for idx in st.session_state.order:
        if idx < file_index:
            new_order.append(idx)
        elif idx > file_index:
            new_order.append(idx - 1)
    st.session_state.order = new_order
    st.session_state.upload_key += 1
    st.rerun()

def chunk_list(seq, chunk_size=7):
    for i in range(0, len(seq), chunk_size):
        yield seq[i:i + chunk_size]

def book_page():
    if "book_generated" not in st.session_state:
        st.session_state.book_generated = False
    if "zip_data" in st.session_state and not st.session_state.book_generated:
        del st.session_state.zip_data
        del st.session_state.zip_filename

    logo_base64 = get_base64_image("logo.png")
    if logo_base64:
        st.markdown(f"""
            <div style="text-align:center;">
                <img src="data:image/png;base64,{logo_base64}" style="width:230px; margin-bottom:-10px;" />
            </div>
        """, unsafe_allow_html=True)

    st.title("Projeto Toth - Geração de Livros")
    st.write("""
    Selecione as imagens do livro. Você pode selecionar uma ou várias páginas.
    Para cada página, insira a posição desejada e clique em **Mover** para reordenar.
    Se uma página for inserida em uma posição já ocupada, as outras serão deslocadas.
    
    Em seguida, defina:
      - O título do livro, que será o nome do arquivo zipado a ser baixado ou enviado ao Drive;
      - O intervalo de numeração;
      - O número inicial da numeração;
      - O estilo, o alinhamento e a cor da numeração.
    """)

    # Inicializa file_data, order e upload_key se ainda não estiverem definidas
    if 'file_data' not in st.session_state:
        st.session_state.file_data = []
    if 'order' not in st.session_state:
        st.session_state.order = list(range(len(st.session_state.file_data)))
    if 'upload_key' not in st.session_state:
        st.session_state.upload_key = 0

    # Ao fazer o upload, armazenamos também os dados originais para não acumular as modificações
    uploaded_files = st.file_uploader(
        "Escolha as imagens",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"upload_{st.session_state.upload_key}"
    )
    if uploaded_files:
        existing_names = [f["name"] for f in st.session_state.file_data]
        for f in uploaded_files:
            if f.name not in existing_names:
                bytes_data = f.read()
                st.session_state.file_data.append({
                    "name": f.name,
                    "original_data": bytes_data,   # Armazena a imagem original
                    "data": bytes_data             # Inicialmente, data é idêntica à original
                })
                st.session_state.order.append(len(st.session_state.file_data) - 1)

    st.markdown("""
    <style>
    /* Cartão que agrupa imagem, posição e botões */
    .my-card {
        background-color: #2C2F33;
        border: 1px solid #444;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
        text-align: center;
    }
    /* Botões personalizados */
    .my-button > button {
        background-color: #5865F2;
        border: none;
        border-radius: 6px;
        color: #ffffff;
        font-weight: 600;
        padding: 0.6rem 1rem;
        cursor: pointer;
        width: 100%;
        margin: 5px 0;
        text-align: center !important;
    }
    .my-button > button:hover {
        background-color: #4752C4;
    }
    /* Centraliza o label dos inputs numéricos */
    div[data-baseweb="input"] label {
        display: block;
        text-align: center;
        margin-bottom: 5px;
        font-weight: 600;
    }
    /* Centraliza o próprio input numérico */
    div[data-baseweb="input"] input {
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

    if st.session_state.file_data:
        order = st.session_state.order
        st.write("### Reordene as páginas (7 por linha)")
        for row_chunk in chunk_list(order, 7):
            cols = st.columns(len(row_chunk))
            st.markdown(
                "<hr style='border: none; border-top: 1px dashed #bbb; margin: 20px 0;'>",
                unsafe_allow_html=True
            )
            for idx, col in enumerate(cols):
                file_index = row_chunk[idx]
                f_dict = st.session_state.file_data[file_index]
                
                if col.button("🗑  Excluir", key=f"delete_{file_index}"):
                    remove_page(file_index)
                
                image = Image.open(io.BytesIO(f_dict["data"]))
                col.image(image, use_container_width=True)
                current_position = order.index(file_index) + 1
                new_pos = col.number_input("Posição", min_value=1, max_value=len(order), value=current_position, key=f"pos_{file_index}")
                if col.button("↔ Mover", key=f"update_{file_index}"):
                    move_page(file_index, new_pos)
    
        st.write("### Defina o título do Livro")
        book_name = st.text_input("Digite o nome do livro:", value="MeuLivro")
        num_pages = len(order)
        
        st.write("### Defina a numeração")
        num_start = st.number_input("Início da numeração (posição)", min_value=1, max_value=num_pages, value=1, key="num_start")
        num_end = st.number_input("Última página a ser numerada (posição)", min_value=1, max_value=num_pages, value=num_pages, key="num_end")
        if num_start > num_end:
            st.error("O início não pode ser maior que o fim.")
        initial_number = st.number_input("Número inicial", min_value=1, value=1, key="initial_number")
        
        if "selected_style" not in st.session_state:
            st.session_state["selected_style"] = "Padrão"
            
        number_styles = ["Padrão", "Romano", "Fresco", "Moderno", "Elegante", "Desenhado"]
        number_style = st.session_state.selected_style
        
        style_thumbnails = {
            "Padrão": "thumbs/thumb_padrao.png",
            "Romano": "thumbs/thumb_romano.png",
            "Fresco": "thumbs/thumb_fresco.png",
            "Moderno": "thumbs/thumb_moderno.png",
            "Elegante": "thumbs/thumb_elegante.png",
            "Desenhado": "thumbs/thumb_desenhado.png"
        }
        
        # Se não houver estilo selecionado, define 'Padrão'
        if "selected_style" not in st.session_state:
            st.session_state.selected_style = "Padrão"

        # Título da sessão
        st.markdown("### Escolha o estilo de numeração:")

        # Define quantas colunas por linha
        n_cols = 3
        styles = list(style_thumbnails.keys())

        # Exibe as opções em grade
        for chunk_start in range(0, len(styles), n_cols):
            cols = st.columns(n_cols)
            chunk = styles[chunk_start:chunk_start + n_cols]
            for i, style in enumerate(chunk):
                with cols[i]:
                    st.image(style_thumbnails[style], width=70)
                    if st.button(style, key=f"style_{style}"):
                        st.session_state.selected_style = style
        
        st.write(f"**Estilo selecionado:** {st.session_state.selected_style}")
        
        custom_color = st.color_picker("Escolha a cor para a numeração", value="#FFFFFF")
        alignment = st.selectbox("Alinhamento da numeração", ["Esquerda", "Central", "Direita"], index=1)
    
        include_epub_numbering = st.checkbox("Incluir numeração no EPUB", value=True)
        include_logo = st.checkbox("Incluir logo da editora na capa e última página", value=True)

        # Validação da configuração para forçar nova geração se alterado
        config = {
            "book_name": book_name,
            "num_start": num_start,
            "num_end": num_end,
            "initial_number": initial_number,
            "number_style": number_style,
            "custom_color": custom_color,
            "alignment": alignment,
            "include_epub_numbering": include_epub_numbering,
            "include_logo": include_logo
        }
        new_config_hash = hashlib.md5(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()
        if st.session_state.get("config_hash") != new_config_hash:
            st.session_state.config_hash = new_config_hash
            st.session_state.book_generated = False

        if st.button("Gerar Livro"):
            new_order = st.session_state.order
            # Cria uma cópia dos arquivos sem modificar os dados originais
            reordered_files = [dict(st.session_state.file_data[i]) for i in new_order]
            
            image_list = []
            for pos, file_index in enumerate(new_order, start=1):
                f_dict = st.session_state.file_data[file_index]
                # Sempre utiliza os dados originais para não acumular numerações
                img = Image.open(io.BytesIO(f_dict["original_data"]))
                
                if img.mode != "RGB":
                    img = img.convert("RGB")
                
                if num_start <= pos <= num_end:
                    display_number = initial_number + (pos - num_start)
                    img = add_page_number(img, display_number, alignment, style=number_style, custom_color=custom_color)
                
                if include_logo and (pos == 1 or pos == len(new_order)):
                    img = add_logo_bottom_center(img, logo_path=LOGO_PATH, margin_bottom_cm=1.0, max_logo_width=200)
                
                with io.BytesIO() as output:
                    img.save(output, format="JPEG")
                    # Atualiza os arquivos da cópia temporária somente para geração atual
                    reordered_files[pos - 1]["data"] = output.getvalue()
                
                image_list.append(img)
            
            pdf_bytes = generate_pdf(image_list)
            sangria_pdf_bytes = generate_pdf_sangria(image_list, dpi=300)
            epub_bytes = generate_epub(
                reordered_files,
                num_start,
                num_end,
                initial_number,
                alignment,
                number_style,
                custom_color=custom_color,
                add_numbering=include_epub_numbering
            )
            
            pdf_filename = f"{book_name}.pdf"
            sangria_pdf_filename = f"{book_name}_sangria.pdf"
            epub_filename = "livro.epub"
            zip_filename = f"{book_name}.zip"
            
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, mode="w") as zipf:
                zipf.writestr(pdf_filename, pdf_bytes.getvalue())
                zipf.writestr(sangria_pdf_filename, sangria_pdf_bytes.getvalue())
                zipf.writestr(epub_filename, epub_bytes.getvalue())
            zip_bytes.seek(0)
            
            st.session_state.zip_data = zip_bytes.getvalue()
            st.session_state.zip_filename = zip_filename
            st.session_state.book_generated = True
            
            st.success("Livro gerado com sucesso!")
            st.download_button("Baixar ZIP", data=zip_bytes, file_name=zip_filename, mime="application/zip")
    
    if st.session_state.get("book_generated", False):
        if st.button("Enviar para o Google Drive"):
            folder_id = "1aOIGtkAVjfh5qfxWidgbR-yLp0C4ZzjG"
            file_id = upload_to_drive(st.session_state.zip_data, st.session_state.zip_filename, folder_id=folder_id)
            if file_id:
                drive_link = f"https://drive.google.com/file/d/{file_id}/view"
                st.success(f"Arquivo enviado com sucesso! Nome do arquivo: {book_name}")
                st.markdown(f"✅ [Clique aqui para acessar o arquivo no Google Drive]({drive_link})")
            else:
                st.error("Falha ao enviar para o Google Drive.")

if __name__ == "__main__":
    book_page()
