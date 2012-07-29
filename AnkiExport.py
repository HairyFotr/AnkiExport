"""
Support for pdf, MediaWiki, and (ugly) LaTeX exporting from Anki.

The pdf/LaTeX parts don't work with non-latin fonts. 

For this plugin to work, you must have pdflatex installed and in your path.

To export, open a deck and go to Tools->PDF Export/MediaWiki Export/LaTeX Export.

Source available at:
https://github.com/HairyFotr/AnkiExport

Changelog:
2012-07-29: tested on Ubuntu, put on GitHub
2012-02-11: added MediaWiki format
2011-01-27: first working version
"""
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from ankiqt import mw
from anki import latex
import anki.cards
import re, tempfile, os, sys, subprocess, shutil
import os.path
import codecs

# Yes I'm parsing HTML and LaTeX with horrible regexes... so shoot me.
# And ofcourse it was made mostly to procrastinate form actual learning :)
# Also, this was the first thing I ever wrote in Python

regexps = {
    "startspan"  : re.compile(r'<span[^>]*>(<span class="[^"]+">)?', re.DOTALL | re.IGNORECASE | re.MULTILINE),
    "endspan"    : re.compile(r'</span>$', re.DOTALL | re.IGNORECASE),

    "span"       : re.compile(r"<span([^>]*)>([^<]*)</span>", re.DOTALL | re.IGNORECASE | re.MULTILINE),
    "bold"       : re.compile(r"font-weight", re.DOTALL | re.IGNORECASE),
    "italic"     : re.compile(r"italic", re.DOTALL | re.IGNORECASE),
    "underline"  : re.compile(r"underline", re.DOTALL | re.IGNORECASE),
    "color"      : re.compile(r"color:,,,,,,#,,,,,,([0-9a-fA-F]+)", re.DOTALL | re.IGNORECASE),

    "lateximg"   : re.compile(r'<img src="[^"]+" alt="([^"]+)"[ /]*>', re.DOTALL | re.IGNORECASE),
    "img"        : re.compile(r'<img src="([^"]+)"[ /]*>', re.DOTALL | re.IGNORECASE),

    "br"         : re.compile(r"<br[ /]*>", re.DOTALL | re.IGNORECASE),
    "br2"        : re.compile(r",,,,,,br,,,,,,", re.DOTALL | re.IGNORECASE),

    "dollar"     : re.compile(r"([^\[/\\])([\$]+)([^\]])", re.DOTALL | re.IGNORECASE),

    "standard"   : re.compile(r"\[latex\](.+?)\[/latex\]", re.DOTALL | re.IGNORECASE),
    "expression" : re.compile(r"\[\$\](.+?)\[/\$\]", re.DOTALL | re.IGNORECASE),
    "math"       : re.compile(r"\[\$\$\](.+?)\[/\$\$\]", re.DOTALL | re.IGNORECASE),
    
    "sound"      : re.compile(r"\[sound:(.+?)\]", re.DOTALL | re.IGNORECASE),
    
    "spaces"     : re.compile(r"}[ ]+([^ ])", re.DOTALL | re.IGNORECASE), #latex doesn't render spaces
    
    "square"     : re.compile(r"([\\s]+|^)[\[]", re.DOTALL | re.IGNORECASE | re.MULTILINE),
}
def HTML2LaTeX(text):
    for match in regexps['dollar'].finditer(text):
        text = text.replace(match.group(), match.group(1) + ",,,,,,\\$,,,,,,"*len(match.group(2)) + match.group(3))
        
    text = text.replace("#", ",,,,,,#,,,,,,")
    #text = text.replace("&amp;", ",,,,,,&,,,,,,")
    text = text.replace("&", ",,,,,,&,,,,,,")
    text = text.replace("^", ",,,,,,^,,,,,,")
    
    text = text.replace("_", "\\char95 ") #underscore
    text = text.replace("\\char95 \\char95", "\\char95\\char95")

    for match in regexps['br'].finditer(text):
        text = text.replace(match.group(), ",,,,,,br,,,,,,")
        
    for match in regexps['lateximg'].finditer(text):
        m1 = match.group(1)
        for brmatch in regexps['br2'].finditer(m1):
            m1 = m1.replace(brmatch.group(), "\n")
        m1 = m1.replace(u'\xb0', "^{\circ}") #degree
        m1 = m1.replace(",,,,,,&,,,,,,amp;", "&")
        m1 = m1.replace(",,,,,,&,,,,,,quot;", "''") #FIXME
        m1 = m1.replace(",,,,,,&,,,,,,", "&")
        m1 = m1.replace('\\char95', "_") #underscore
        m1 = m1.replace('\\char95 ', "_") #underscore
        m1 = m1.replace(",,,,,,#,,,,,,", "#")
        m1 = m1.replace(",,,,,,^,,,,,,", "^")
        m1 = m1.replace('\\$', "$")
        m1 = m1
        text = text.replace(match.group(), m1)

    for match in regexps['span'].finditer(text):
        prefix = postfix = ''
        
        if regexps['bold'].search(match.group(1)) != None:
            prefix += "\\textbf{"
            postfix += "}"
        if regexps['italic'].search(match.group(1)) != None:
            prefix += "\\textit{"
            postfix += "}"
        if regexps['underline'].search(match.group(1)) != None:
            prefix += "\\underline{"
            postfix += "}"
        m = regexps['color'].search(match.group(1))
        if m != None:
            csplit = (m.group(1)[0:2], m.group(1)[2:4], m.group(1)[4:6])
            colors = [str(int(x, 16)) for x in csplit]
            prefix += "{\\color[RGB]{"+colors[0]+","+colors[1]+","+colors[2]+"}"
            postfix += "}"
        
        m2 = match.group(2)
        if len(prefix)>0:
            for brmatch in regexps['br2'].finditer(m2):
                m2 = m2.replace(brmatch.group(), postfix+" \\ \\\\ "+prefix) #can't break line inside environments
            
        text = text.replace(match.group(), prefix+m2+postfix)        

    for match in regexps['img'].finditer(text):
        m1 = match.group(1)
        m1 = m1.replace('\\char95 ', "_") #underscore
        m1 = m1.replace('\\char95', "_") #underscore
        text = text.replace(match.group(), "\\includegraphics*[scale=0.5]{"+m1+"}")
        
    for match in regexps['standard'].finditer(text):
        m1 = match.group(1)
        m1 = m1.replace(',,,,,,\\$,,,,,,', "$")
        m1 = m1.replace('\\char95 ', "_") #underscore
        m1 = m1.replace('\\char95', "_") #underscore
        m1 = m1.replace(",,,,,,#,,,,,,", "#")
        m1 = m1.replace(",,,,,,&,,,,,,amp;", "&")
        m1 = m1.replace(",,,,,,&,,,,,,quot;", "''") #FIXME
        m1 = m1.replace(",,,,,,&,,,,,,", "&")
        m1 = m1.replace(",,,,,,^,,,,,,", "^")
        text = text.replace(match.group(), "{"+m1+"}")

    for match in regexps['expression'].finditer(text):
        m1 = match.group(1)
        for brmatch in regexps['br2'].finditer(m1):
            m1 = m1.replace(brmatch.group(), "\n")
        m1 = m1.replace(u'\xb0', "^{\circ}") #degree
        m1 = m1.replace(",,,,,,&,,,,,,amp;", "&")
        m1 = m1.replace(",,,,,,&,,,,,,quot;", "''") #FIXME
        m1 = m1.replace(",,,,,,&,,,,,,", "&")
        m1 = m1.replace('\\char95', "_") #underscore
        m1 = m1.replace(",,,,,,#,,,,,,", "#")
        m1 = m1.replace(",,,,,,^,,,,,,", "^")
        text = text.replace(match.group(), "{$"+m1+"$}")
	   
    for match in regexps['math'].finditer(text):
        m1 = match.group(1)
        for brmatch in regexps['br2'].finditer(m1):
            m1 = m1.replace(brmatch.group(), "\n")
        m1 = m1.replace(u'\xb0', "^{\circ}") #degree
        m1 = m1.replace(",,,,,,&,,,,,,amp;", "&")
        m1 = m1.replace(",,,,,,&,,,,,,quot;", "''") #FIXME
        m1 = m1.replace(",,,,,,&,,,,,,", "&")
        m1 = m1.replace('\\char95', "_") #underscore
        m1 = m1.replace(",,,,,,#,,,,,,", "#")
        m1 = m1.replace(",,,,,,^,,,,,,", "^")
        text = text.replace(match.group(), "{\\begin{displaymath}"+m1+"\\end{displaymath}}")

    for match in regexps['br2'].finditer(text):
        text = text.replace(match.group(), " \\ \\\\ \n")

    #just some chars I ran into... a horrible solution
    text = text.replace(",,,,,,&,,,,,,amp;", "\\&")
    text = text.replace(",,,,,,&,,,,,,quot;", "''") #FIXME
    text = text.replace(",,,,,,&,,,,,,", "\\&")
    text = text.replace(",,,,,,#,,,,,,", "\\#")
    
    text = text.replace("\\&gt;", ">")
    text = text.replace("\\&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&lt;", "<")
    text = text.replace(",,,,,,^,,,,,,", "\\^{}")

    #greek letters
    text = text.replace(u'\u0251', "$\\alpha$")
    text = text.replace(u'\u00B5', "$\\mu$")
    
    gtexchars = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu", 
    "nu", "xi", "o", "pi", "rho", "varsigma", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega")
    base = int("0x03B1",16)
    for gtex in gtexchars:
        gutf = unichr(base)
        text = text.replace(gutf, "$\\"+gtex+"$")
        base+=1
        
    #arrows
    text = text.replace(u'\u2190', "$\\leftarrow$")
    text = text.replace(u'\u2191', "$\\uparrow$")
    text = text.replace(u'\u2192', "$\\rightarrow$")
    text = text.replace(u'\u2193', "$\\downarrow$")
    
    text = text.replace(',,,,,,\\$,,,,,,', "\\$")
    text = text.replace(u'\xb0', "$\\,^{\circ}$") #degree
    text = text.replace(u'\xb9', "$\\,^{1}$") #^1
    text = text.replace(u'\xb2', "$\\,^{2}$") #^2
    text = text.replace(u'\xb3', "$\\,^{3}$") #^3

    text = text.replace(u'\u20ac', "$\\in$") #euro (real one requires additional latex package)
    text = text.replace(u'\xa3', "\\textsterling") #pound
    text = text.replace(u'\xa5', "Y") #yen hack (real one requires additional latex package)
    
    #if I somehow forgot to parse some hack char
    text = text.replace(',,,,,,', '');
    
    
    latexchars = ["%"]
    for lchar in latexchars:
        text = text.replace(lchar, "\\"+lchar);

    for match in regexps['startspan'].finditer(text):
        text = text.replace(match.group(), "")
    
    for match in regexps['endspan'].finditer(text):
        text = text.replace(match.group(), "")

    for match in regexps['sound'].finditer(text):
        text = text.replace(match.group(), "")

    for match in regexps['spaces'].finditer(text):
        text = text.replace(match.group(), "}\\ "+match.group(1))

    for match in regexps['square'].finditer(text):
        text = text.replace(match.group(), match.group(1)+"{[}") #(newline)\\[length] is not what I want {[} fixes it
        
    return text
    
def deck2LaTeX(deck):
    """convert deck to LaTeX format"""
    mdir = deck.mediaDir()
    if not mdir:
        latexPreamble = (
                         "\\documentclass[a4paper]{article}\n"
                         "\\usepackage{grffile}\n"
                         "\\usepackage{graphicx}\n"
                         "\\usepackage{amsmath,amssymb}\n"
                         "\\usepackage[utf8]{inputenc}\n"
                         "\\usepackage[T1]{fontenc}\n"
                         "\\pagestyle{empty}\n"
                         "\\usepackage{color}\n"
                         "\\usepackage[left=2cm,top=2cm,right=2cm,bottom=2cm]{geometry}"

                         "\\begin{document}\n"
                         "\\begin{center}\n"                 
                         )
    else:
        latexPreamble = (
                         "\\documentclass[a4paper]{article}\n"
                         "\\usepackage{grffile}\n"
                         "\\usepackage{graphicx}\n"
                         "\\graphicspath{{"+deck.mediaDir().replace("\\", "/")+"/}}\n"
                         "\\usepackage{amsmath,amssymb}\n"
                         "\\usepackage[utf8]{inputenc}\n"
                         "\\usepackage[T1]{fontenc}\n"
                         "\\pagestyle{empty}\n"
                         "\\usepackage{color}\n"
                         "\\usepackage[left=2cm,top=2cm,right=2cm,bottom=2cm]{geometry}"

                         "\\begin{document}\n"
                         "\\begin{center}\n"                 
                         )
    
    latexPostamble = (
                     "\\end{center}\n"
                     "\\end{document}\n"
                     )

    deckLatex = ''
    cardids = deck.s.column0("select id from cards order by created")
    for c, cardid in enumerate(cardids):
        card = deck.s.query(anki.cards.Card).get(cardid)	 
        deckLatex += HTML2LaTeX(card.question)+" \\ \\\\ --- \\ \\\\ \n"
        deckLatex += HTML2LaTeX(card.answer)+" \\ \\\\ \\ \\\\ \n"
        deckLatex += " \\hrule \\ \\\\ \n"
    
    return latexPreamble + "\n" + deckLatex + "\n" + latexPostamble + "\n"

regexpsMW = {
    "color"      : re.compile(r"color:#([0-9a-fA-F]+)", re.DOTALL | re.IGNORECASE),
    "br"         : re.compile(r"<br[ /]*>", re.DOTALL | re.IGNORECASE),
}

def HTML2MediaWiki(text):
    for match in regexps['lateximg'].finditer(text):
        m1 = match.group(1)
        for brmatch in regexpsMW['br'].finditer(m1):
            m1 = m1.replace(brmatch.group(), ",,,,n,,,,")
        m1 = m1.replace("&amp;", "&")
        m1 = m1.replace('\\$', "$")
        m1 = '<math>' + m1[1:-1] + '</math>'
        text = text.replace(match.group(), m1)

    black = True
    for match in regexps['span'].finditer(text):
        if(len(match.group(2).strip())>0):
            prefix = postfix = ''
            
            if regexps['bold'].search(match.group(1)) != None:
                prefix = "'''"+prefix
                postfix += "'''"
            if regexps['italic'].search(match.group(1)) != None:
                prefix = "''"+prefix
                postfix += "''"
            if regexps['underline'].search(match.group(1)) != None:
                prefix = "<u>"+prefix
                postfix += "</u>"
            m = regexpsMW['color'].search(match.group(1))
            if m != None:
                if(m.group(1)!='000000'):
                    prefix = "<,.,,,,,,,,., style='color:#"+m.group(1)+"'>"+prefix
                    postfix += "</,.,,,,,,,,.,>"
                    black = False
                elif(m.group(1)=='000000' and not black):
                    prefix = "<,.,,,,,,,,., style='color:#"+m.group(1)+"'>"+prefix
                    postfix += "</,.,,,,,,,,.,>"
                    black = True
            
            text = text.replace(match.group(), prefix+match.group(2)+postfix)        

    for match in regexps['img'].finditer(text):
        text = text.replace(match.group(), "[[Image:anki_"+mw.deck.name()+"_"+match.group(1)+"]]")

    for match in regexps['startspan'].finditer(text):
        text = text.replace(match.group(), "")
    
    for match in regexps['endspan'].finditer(text):
        text = text.replace(match.group(), "")
        
    text = text.replace(",.,,,,,,,,.,", "span")

    for match in regexps['sound'].finditer(text):
        text = text.replace(match.group(), "")

    text = text.replace("<br>", "<br />")
    text = text.replace("\n", "<br />")
    text = text.replace("<br />", "<br />\n")
    text = text.replace(",,,,n,,,,", "\n")    
    
    while(text.endswith("<br />") or text.endswith("\n")):
        text = text.strip(" \n\t")
        text = text[:len(text)-len("<br />")]

    text = "\n".join([s.strip() for s in text.split("\n")])

    return text
    
def deck2MediaWiki(deck):
    """convert deck to MediaWiki format"""
    
    mdir = deck.mediaDir()
    deckMW = ''
    cardids = deck.s.column0("select id from cards order by created")

    first = True;
    for c, cardid in enumerate(cardids):
        card = deck.s.query(anki.cards.Card).get(cardid)	 

        if first:
            first = False;
        else:
            deckMW += "\n\n----\n\n"

        deckMW += "<big>" + HTML2MediaWiki(card.question)+"</big><br /><br />\n\n"
        deckMW += HTML2MediaWiki(card.answer)
       
    return deckMW

def writeFile(path, text):
    texfile = codecs.open(path, "w+", "utf-8")
    texfile.write(text)
    texfile.close()

def writePdf(path, latexstr):
    tmptex = "tmp.tex"
    tmppdf = "tmp.pdf"
    oldcwd = os.getcwd()
    try:
        os.chdir(tmpdir)
        writeFile(tmptex, latexstr)
        if os.path.isfile(os.path.join(tmpdir, tmptex)):
            #latex.call(['pdflatex', "-interaction=nonstopmode", tmptex])
            latex.call(["pdflatex", tmptex])
            
            if os.path.isfile(os.path.join(tmpdir, tmppdf)):
                shutil.copy2(tmppdf, path)
    finally:
        os.chdir(oldcwd)    

masks = {
    'pdf' : ['Export to PDF', 'PDF document (*.pdf)'],
    'latex' : ['Export to LaTeX', 'LaTeX document (*.tex)'],
    'wiki' : ['Export to MediaWiki', 'Text document (*.txt)'],
}
def saveDialog(mask, name='export'):
    return unicode(QFileDialog.getSaveFileName(mw, mask[0], os.path.join(str(QDir.homePath()), "anki_"+name), mask[1]))

def pdfExport():
    filename = saveDialog(masks['pdf'], mw.deck.name())
    mw.deck.startProgress()
    if len(filename)!=0:
        writePdf(filename, deck2LaTeX(mw.deck))
    mw.deck.finishProgress()
    
def latexExport():
    filename = saveDialog(masks['latex'], mw.deck.name())
    if len(filename)!=0:
        writeFile(filename, deck2LaTeX(mw.deck))

def MWExport():
    filename = saveDialog(masks['wiki'], mw.deck.name())
    if len(filename)!=0:
        writeFile(filename, deck2MediaWiki(mw.deck))
    
def addMenu():
    a = QAction(mw)
    a.setText("PDF Export")
    mw.mainWin.menuTools.addAction(a)
    mw.connect(a, SIGNAL("triggered()"), pdfExport)

    a = QAction(mw)
    a.setText("LaTeX Export")
    mw.mainWin.menuTools.addAction(a)
    mw.connect(a, SIGNAL("triggered()"), latexExport)

    a = QAction(mw)
    a.setText("MediaWiki Export")
    mw.mainWin.menuTools.addAction(a)
    mw.connect(a, SIGNAL("triggered()"), MWExport)
    
    
tmpdir = tempfile.mkdtemp(prefix="anki")
mw.addHook("init", addMenu)
