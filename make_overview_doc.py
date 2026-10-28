"""Build a compact Word outline using standard OOXML parts."""

# Use only the standard library so the document can be built in this workspace.
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


# Keep the outline to one page with a title, purpose, and eight bullets.
OUTPUT = Path(__file__).with_name("diffusion_estimator_app_overview.docx")
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def paragraph(text, style=None, bullet=False):
    """Return one escaped Word paragraph with optional style and bullet."""
    # Apply a named style to titles and headings, and numbered-list metadata to bullets.
    properties = f'<w:pStyle w:val="{escape(style)}"/>' if style else ""
    if bullet:
        properties += '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    properties = f"<w:pPr>{properties}</w:pPr>" if properties else ""
    return f'<w:p>{properties}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>'


# State the model's purpose before grouping the key data, workflow, and code locations.
body = [
    paragraph("Diffusion Estimator App Overview", "Title"),
    paragraph("A starting outline of how the app prepares inputs and predicts crop arrival times."),
    paragraph("Data processing", "Heading1"),
    paragraph(
        "Raw crop records and geographic and climate sources from bottlenecks become HDF5 files for crop sites and environmental layers.",
        bullet=True,
    ),
    paragraph(
        "Temperature and PRECC precipitation retain native-grid frames every 100 years; sea is saved as a categorical 0.5 degree mask.",
        bullet=True,
    ),
    paragraph(
        "Loading averages climate frames across the crop years, resamples layers to the chosen delta, standardizes continuous maps globally, and crops to the study area. Sea uses nearest-neighbour sampling without normalization.",
        bullet=True,
    ),
    paragraph("Model workflow", "Heading1"),
    paragraph(
        "DiffusionEstimator places crop sites and selected layers on one grid, then builds a sigmoid speed map from the intercept and layer coefficients.",
        bullet=True,
    ),
    paragraph(
        "Monte Carlo averages simulated first-arrival times; fast marching calculates deterministic arrival times. Both apply W = cos(latitude) by default.",
        bullet=True,
    ),
    paragraph(
        "Predicted and observed arrival times produce mean squared error; sweep_theta and fit_theta explore model coefficients.",
        bullet=True,
    ),
    paragraph("Repository layout", "Heading1"),
    paragraph(
        "processing/ loads HDF5 inputs and rebuilds sea and precipitation; data/processed/ holds crop and layer files.",
        bullet=True,
    ),
    paragraph(
        "diffusion_estimator.py is the main API; monte_carlo.py and fast_marching.py are the solvers; layer_inspection.ipynb, plotting/, and tests/ support inspection and checks.",
        bullet=True,
    ),
]


# Set a conventional A4 page and compact black typography in the Word package.
document = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:document xmlns:w="{WORD_NS}" xmlns:r="{OFFICE_REL_NS}"><w:body>'
    + "".join(body)
    + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1170" w:right="1250" w:bottom="1170" w:left="1250"/>'
    '</w:sectPr></w:body></w:document>'
)
styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{WORD_NS}">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
<w:name w:val="Normal"/><w:pPr><w:spacing w:after="110" w:line="280" w:lineRule="auto"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:color w:val="000000"/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="180"/></w:pPr>
<w:rPr><w:b/><w:rFonts w:ascii="Aptos Display" w:hAnsi="Aptos Display"/><w:color w:val="000000"/><w:sz w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="225" w:after="80"/></w:pPr>
<w:rPr><w:b/><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:color w:val="000000"/><w:sz w:val="24"/></w:rPr></w:style>
</w:styles>'''
numbering = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{WORD_NS}"><w:abstractNum w:abstractNumId="0">
<w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0">
<w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/>
<w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="690"/></w:tabs>
<w:ind w:left="690" w:hanging="300"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/></w:rPr>
</w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'''


# Declare the required package parts and their relationships for Word readers.
content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''
relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
<Relationship Id="rId1" Type="{OFFICE_REL_NS}/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="{OFFICE_REL_NS}/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''
document_relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
<Relationship Id="rId1" Type="{OFFICE_REL_NS}/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="{OFFICE_REL_NS}/numbering" Target="numbering.xml"/>
</Relationships>'''
core = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Diffusion Estimator App Overview</dc:title></cp:coreProperties>'''
app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
<Application>Microsoft Office Word</Application></Properties>'''


# Write each XML part into a single valid DOCX archive.
with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as archive:
    for name, content in {
        "[Content_Types].xml": content_types,
        "_rels/.rels": relationships,
        "word/document.xml": document,
        "word/styles.xml": styles,
        "word/numbering.xml": numbering,
        "word/_rels/document.xml.rels": document_relationships,
        "docProps/core.xml": core,
        "docProps/app.xml": app,
    }.items():
        archive.writestr(name, content.encode("utf-8"))

print(OUTPUT)
