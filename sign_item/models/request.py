# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import io
import time

from PyPDF2 import PdfFileReader, PdfFileWriter
try:
    from PyPDF2.errors import PdfReadError
except ImportError:
    from PyPDF2.utils import PdfReadError
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.rl_config import TTFSearchPath
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase.pdfmetrics import stringWidth
from werkzeug.urls import url_join, url_quote
from random import randint
from markupsafe import Markup
from hashlib import sha256
from PIL import UnidentifiedImageError

from odoo import api, fields, models, http, _, Command
from odoo.tools import config, email_normalize, get_lang, is_html_empty, format_date, formataddr, groupby
from odoo.exceptions import UserError, ValidationError

def _fix_image_transparency(image):
    """ Modify image transparency to minimize issue of grey bar artefact.

    When an image has a transparent pixel zone next to white pixel zone on a
    white background, this may cause on some renderer grey line artefacts at
    the edge between white and transparent.

    This method sets transparent pixel to white transparent pixel which solves
    the issue for the most probable case. With this the issue happen for a
    black zone on black background but this is less likely to happen.
    """
    pixels = image.load()
    for x in range(image.size[0]):
        for y in range(image.size[1]):
            if pixels[x, y] == (0, 0, 0, 0):
                pixels[x, y] = (255, 255, 255, 0)

class Request(models.Model):
    _inherit = "sign.request"

    def _generate_completed_document(self, password=""):
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_("The completed document cannot be created because the sign request is not fully signed"))
        if not self.template_id.sign_item_ids:
            self.completed_document = self.template_id.attachment_id.datas
        else:
            try:
                old_pdf = PdfFileReader(io.BytesIO(base64.b64decode(self.template_id.attachment_id.datas)), strict=False, overwriteWarnings=False)
                old_pdf.getNumPages()
            except:
                raise ValidationError(_("ERROR: Invalid PDF file!"))

            isEncrypted = old_pdf.isEncrypted
            if isEncrypted and not old_pdf.decrypt(password):
                # password is not correct
                return

            font = self._get_font()
            normalFontSize = self._get_normal_font_size()

            packet = io.BytesIO()
            can = canvas.Canvas(packet)
            itemsByPage = self.template_id._get_sign_items_by_page()
            items_ids = [id for items in itemsByPage.values() for id in items.ids]
            values_dict = self.env['sign.request.item.value'].read_group(
                [('sign_item_id', 'in', items_ids), ('sign_request_id', '=', self.id)],
                fields=['value:array_agg', 'frame_value:array_agg', 'frame_has_hash:array_agg'],
                groupby=['sign_item_id']
            )
            values = {
                val['sign_item_id'][0]: {
                    'value': val['value'][0],
                    'frame': val['frame_value'][0],
                    'frame_has_hash': val['frame_has_hash'][0],
                } for val in values_dict if 'value' in val
            }

            for p in range(0, old_pdf.getNumPages()):
                page = old_pdf.getPage(p)
                # Absolute values are taken as it depends on the MediaBox template PDF metadata, they may be negative
                width = float(abs(page.mediaBox.getWidth()))
                height = float(abs(page.mediaBox.getHeight()))

                # Set page orientation (either 0, 90, 180 or 270)
                rotation = page['/Rotate'] if '/Rotate' in page else 0
                if rotation and isinstance(rotation, int):
                    can.rotate(rotation)
                    # Translate system so that elements are placed correctly
                    # despite the orientation
                    if rotation == 90:
                        width, height = height, width
                        can.translate(0, -height)
                    elif rotation == 180:
                        can.translate(-width, -height)
                    elif rotation == 270:
                        width, height = height, width
                        can.translate(-width, 0)

                items = itemsByPage[p + 1] if p + 1 in itemsByPage else []
                for item in items:
                    value_dict = values.get(item.id)
                    if not value_dict:
                        continue
                    # only get the 1st
                    value = value_dict['value']
                    frame = value_dict['frame']

                    if frame:
                        try:
                            image_reader = ImageReader(io.BytesIO(base64.b64decode(frame[frame.find(',')+1:])))
                        except UnidentifiedImageError:
                            raise ValidationError(_("There was an issue downloading your document. Please contact an administrator."))
                        _fix_image_transparency(image_reader._image)
                        can.drawImage(
                            image_reader,
                            width*item.posX,
                            height*(1-item.posY-item.height),
                            width*item.width,
                            height*item.height,
                            'auto',
                            True
                        )

                    if item.type_id.item_type == "text":
                        value = self._get_displayed_text(value)
                        can.setFont(font, height*item.height*0.8)
                        if item.alignment == "left":
                            can.drawString(width*item.posX, height*(1-item.posY-item.height*0.9), value)
                        elif item.alignment == "right":
                            can.drawRightString(width*(item.posX+item.width), height*(1-item.posY-item.height*0.9), value)
                        else:
                            can.drawCentredString(width*(item.posX+item.width/2), height*(1-item.posY-item.height*0.9), value)

                    elif item.type_id.item_type == "selection":
                        content = []
                        for option in item.option_ids:
                            if option.id != int(value):
                                content.append("<strike>%s</strike>" % (option.value))
                            else:
                                content.append(option.value)
                        font_size = height * normalFontSize * 0.8
                        can.setFont(font, font_size)
                        text = " / ".join(content)
                        string_width = stringWidth(text.replace("<strike>", "").replace("</strike>", ""), font, font_size)
                        p = Paragraph(text, getSampleStyleSheet()["Normal"])
                        posX = width * (item.posX + item.width * 0.5) - string_width // 2
                        posY = height * (1 - item.posY - item.height * 0.5) - p.wrap(width, height)[1] // 2
                        p.drawOn(can, posX, posY)

                    elif item.type_id.item_type == "textarea":
                        can.setFont(font, height*normalFontSize*0.8)
                        lines = value.split('\n')
                        y = (1-item.posY)
                        for line in lines:
                            y -= normalFontSize*0.9
                            can.drawString(width*item.posX, height*y, line)
                            y -= normalFontSize*0.1

                    elif item.type_id.item_type == "checkbox":
                        can.setFont(font, height*item.height*0.8)
                        value = 'X' if value == 'on' else ''
                        can.drawString(width*item.posX, height*(1-item.posY-item.height*0.9), value)

                    elif item.type_id.item_type == "signature" or item.type_id.item_type == "initial":
                        try:
                            image_reader = ImageReader(io.BytesIO(base64.b64decode(value[value.find(',')+1:])))
                        except UnidentifiedImageError:
                            raise ValidationError(_("There was an issue downloading your document. Please contact an administrator."))
                        _fix_image_transparency(image_reader._image)
                        can.drawImage(image_reader, width*item.posX, height*(1-item.posY-item.height), width*item.width, height*item.height, 'auto', True)

                    # Nuevo bloque elif para item.type_id.item_type == "sequential"
                    elif item.type_id.item_type == "sequential":
                        value = self._get_displayed_text(value)
                        can.setFont(font, height*item.height*0.8)
                        if item.alignment == "left":
                            can.drawString(width*item.posX, height*(1-item.posY-item.height*0.9), value)
                        elif item.alignment == "right":
                            can.drawRightString(width*(item.posX+item.width), height*(1-item.posY-item.height*0.9), value)
                        else:
                            can.drawCentredString(width*(item.posX+item.width/2), height*(1-item.posY-item.height*0.9), value)

                can.showPage()

            can.save()

            item_pdf = PdfFileReader(packet, overwriteWarnings=False)
            new_pdf = PdfFileWriter()

            for p in range(0, old_pdf.getNumPages()):
                page = old_pdf.getPage(p)
                page.mergePage(item_pdf.getPage(p))
                new_pdf.addPage(page)

            if isEncrypted:
                new_pdf.encrypt(password)

            try:
                output = io.BytesIO()
                new_pdf.write(output)
            except PdfReadError:
                raise ValidationError(_("There was an issue downloading your document. Please contact an administrator."))

            self.completed_document = base64.b64encode(output.getvalue())
            output.close()

        attachment = self.env['ir.attachment'].create({
            'name': "%s.pdf" % self.reference if self.reference.split('.')[-1] != 'pdf' else self.reference,
            'datas': self.completed_document,
            'type': 'binary',
            'res_model': self._name,
            'res_id': self.id,
        })

        # print the report with the public user in a sudoed env
        # public user because we don't want groups to pollute the result
        # (e.g. if the current user has the group Sign Manager,
        # some private information will be sent to *all* signers)
        # sudoed env because we have checked access higher up the stack
        public_user = self.env.ref('base.public_user', raise_if_not_found=False)
        if not public_user:
            # public user was deleted, fallback to avoid crash (info may leak)
            public_user = self.env.user
        pdf_content, __ = self.env["ir.actions.report"].with_user(public_user).sudo()._render_qweb_pdf(
            'sign.action_sign_request_print_logs',
            self.ids,
            data={'format_date': format_date, 'company_id': self.communication_company_id}
        )
        attachment_log = self.env['ir.attachment'].create({
            'name': "Certificate of completion - %s.pdf" % time.strftime('%Y-%m-%d - %H:%M:%S'),
            'raw': pdf_content,
            'type': 'binary',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.completed_document_attachment_ids = [Command.set([attachment.id, attachment_log.id])]