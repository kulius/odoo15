# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime
import tempfile
import binascii
from datetime import date, datetime
from odoo.exceptions import Warning, UserError
from odoo import models, fields, exceptions, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT

import logging
_logger = logging.getLogger(__name__)
import io
try:
	import xlrd
except ImportError:
	_logger.debug('Cannot `import xlrd`.')
try:
	import csv
except ImportError:
	_logger.debug('Cannot `import csv`.')
try:
	import xlwt
except ImportError:
	_logger.debug('Cannot `import xlwt`.')
try:
	import cStringIO
except ImportError:
	_logger.debug('Cannot `import cStringIO`.')
try:
	import base64
except ImportError:
	_logger.debug('Cannot `import base64`.')

class ImportAccountsale(models.TransientModel):
	_name = "import.account.sale"

	def _get_default_journal(self):
		domain = [('company_id', '=', self.env.company.id), ('type', '=', 'sale')]
		journal = self.env['account.journal'].search(domain, order="id", limit=1)
		return journal

	journal_id = fields.Many2one('account.journal', string='日記帳',domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]", default=_get_default_journal)
	company_id = fields.Many2one('res.company', string='所屬公司', required=True,
								 default=lambda self: self.env.company)
	file_slect = fields.Binary(string="選擇檔案")
	file_name = fields.Char(string="檔案名稱")

	#匯入發票明細(訂單明細)
	def imoport_file_sale(self):
		try:
			fp = tempfile.NamedTemporaryFile(delete= False,suffix=".xlsx")
			fp.write(binascii.a2b_base64(self.file_slect))
			fp.seek(0)
			values = {}
			workbook = xlrd.open_workbook(fp.name)
			worksheet = workbook.sheet_by_index(0)

			first_row = []  # The row where we stock the name of the column
			for col in range(worksheet.ncols):
				first_row.append(worksheet.cell_value(0, col))
			# transform the workbook to a list of dictionaries
			archive_lines = []
			for row in range(1, worksheet.nrows):
				elm = {}
				for col in range(worksheet.ncols):
					elm[first_row[col]] = worksheet.cell_value(row, col)

				archive_lines.append(elm)

		except:
			raise Warning(_("Invalid file!"))

		cont = 0
		for line in archive_lines:
			cont += 1
			acc_sale_no = str(line.get(u'產品編號', "")).strip()
			if len(acc_sale_no) >= 10:
				partner_name = str(line.get(u'小計', "")).strip()
				partner_id = self.find_partner(partner_name)  # 尋找客戶編號
				acc_id = None #若 銷售單 大於10碼 表示為 銷售單，清空後繼續尋找
				acc_id = self.find_acc(acc_sale_no, partner_id, line)
				continue

			if len(acc_sale_no) < 10 and acc_id:
				product_id = None
				product_tmp_id, product_id = self.find_product(line)

				quantity = line.get(u'數量', 0)
				price_unit = self.get_valid_price(line.get(u'單價', ""), cont)
			# product_name = product_id.name +' '+ str(line.get(u'採購量', "")).strip()+'*'+str(line.get(u'單價', "")).strip()
			# accno = str(line.get(u'代號', "")).strip().replace('.0','')
			# acc_serach = self.env['account.account'].search([('code', '=', accno)])

			if acc_id and product_id:
				vals = [{
					#'move_id': acc_id.id,
					'parent_state': 'draft',
					'product_id': product_id.id,
					# 'product_uom_qty': float(quantity),
					'quantity': float(quantity),
					'price_unit': price_unit,
					'tax_ids': None,
					# 'debit': price_unit,
					# 'credit': price_unit,
					#'tax_id': [(6, 0, self.tax_id)],
				}]
				acc_id.write({'invoice_line_ids': [(0, 0, x) for x in vals]})

		return {'type': 'ir.actions.act_window_close'}

	#匯入發票
	def imoport_file(self):
		try:
			fp = tempfile.NamedTemporaryFile(delete= False,suffix=".xlsx")
			fp.write(binascii.a2b_base64(self.file_slect))
			fp.seek(0)
			values = {}
			workbook = xlrd.open_workbook(fp.name)
			worksheet = workbook.sheet_by_index(0)

			first_row = []  # The row where we stock the name of the column
			for col in range(worksheet.ncols):
				first_row.append(worksheet.cell_value(0, col))
			# transform the workbook to a list of dictionaries
			archive_lines = []
			for row in range(1, worksheet.nrows):
				elm = {}
				for col in range(worksheet.ncols):
					elm[first_row[col]] = worksheet.cell_value(row, col)

				archive_lines.append(elm)

		except:
			raise Warning(_("Invalid file!"))

		self.valid_columns_keys(archive_lines) #檢查

		cont = 0
		for line in archive_lines:
			cont += 1
			partner_name = str(line.get(u'客戶姓名', "")).strip()
			partner_id = self.find_partner(partner_name) # 尋找客戶編號
			acc_sale_no = str(line.get(u'銷售單', "")).strip()
			acc_id = self.find_acc(acc_sale_no, partner_id, line)
		return {'type': 'ir.actions.act_window_close'}

	#尋找客戶，若無則建立
	def find_product(self, importline):
		p_code = str(importline.get(u'產品編號', "")).strip()
		p_name = str(importline.get(u'描述', "")).strip()
		p_standard_price = str(importline.get(u'單價', "")).strip()

		product_tmp_search = self.env['product.template'].search([('default_code', '=', p_code)])

		if product_tmp_search:
			product_search = self.env['product.product'].search([('product_tmpl_id', '=', product_tmp_search.id)])
			return product_tmp_search ,product_search
		else:
			product_tmp_search = self.env['product.template'].create({
				'name': p_name,
				'default_code': p_code,
				'standard_price': p_standard_price if p_standard_price else 0.0,
				'type': 'service',
				'active': True,
				'sale_ok': 'True',
				'taxes_id': None,
				'supplier_taxes_id': None,
			})
			product_search = self.env['product.product'].search([('product_tmpl_id', '=', product_tmp_search.id)])

			return product_tmp_search, product_search
	# 
	# 
	#尋找客戶，若無則建立
	def find_partner(self, partner_name):
		res_partner = self.env['res.partner']
		partner_search = res_partner.search([('name', '=', partner_name)], limit=1)

		if partner_search:
			return partner_search
		else:
			partner_id = res_partner.create({
				'company_type': 'company',
				'name': partner_name,
				})
			return partner_id
	# 
	#尋找訂單，若無則建立
	def find_acc(self, acc_sale_no, partner_id, importline):
		acc_move_obj = self.env['account.move']
		acc_search = acc_move_obj.search([('ref', '=', acc_sale_no)])

		if acc_search:
			return acc_search
		else:
			p_date = str(importline.get(u'結帳日期', "")).strip().split('/')
			acc_id = acc_move_obj.create({
				'state': 'draft',
				'partner_id': partner_id.id,
				'move_type': 'out_invoice',
				# 'name': '/',
				'date': datetime.strptime(p_date[0]+'-'+p_date[1]+'-'+p_date[2], "%Y-%m-%d"),
				'invoice_date': datetime.strptime(p_date[0] + '-' + p_date[1] + '-' + p_date[2], "%Y-%m-%d"),
				#'user_id': self.env.user.partner_id.id,
				'company_id': self.company_id.id,
				'journal_id': self.journal_id.id,
				'payment_reference': str(importline.get(u'發票號碼', "")),
				'ref': acc_sale_no,
				# 'sale_date': str(importline.get(u'進貨日期', "")).strip(),
				# 'bill_no': str(importline.get(u'發票日期', "")).strip().replace('.0',''),
				# 'bill_date': str(importline.get(u'發票號碼', "")).strip(),
				# 'invoice_payment_ref': str(importline.get(u'發票號碼', "")).strip().replace('.0',''),
				# 'import_memo': self.file_name,
				# 'invoice_origin': self.file_name,
				})
			return acc_id

	def valid_columns_keys(self, archive_lines):
		columns = archive_lines[0].keys()
		print
		"columns>>", columns
		text = "匯入必需包含下列欄位:";
		text2 = text
		if not '發票號碼' in columns:
			text += "\n[ 發票號碼 ]"
		if not u'銷售單' in columns:
			text += "\n[ 銷售單 ]"
		if text != text2:
			raise UserError(text)
		return True
	# 
	# 
	# def valid_product_code(self, archive_lines, product_obj):
	# 	cont = 0
	# 	for line in archive_lines:
	# 		cont += 1
	# 		code = str(line.get('商品選項貨號', "")).strip()
	# 		product_id = product_obj.search([('default_code', '=', code)])
	# 		if len(product_id) > 1:
	# 			raise UserError("The product code of line %s is duplicated in the system." % cont)
	# 		if not product_id:
	# 			raise UserError("The product code of line %s can't be found in the system." % cont)
	# 
	def get_valid_price(self, price, cont):
		if price != "":
			price = str(price).replace("$", "").replace(",", ".")
		try:
			price_float = float(price)
			return price_float
		except:
			raise UserError(
				"The price of the line item %s does not have an appropriate format, for example: '100.00' - '100" % cont)
		return False


# 	def create_chart_accounts(self,values):
#
# 		if values.get("code") == "":
# 			raise Warning(_('Code field cannot be empty.') )
#
# 		if values.get("name") == "":
# 			raise Warning(_('Name field cannot be empty.') )
#
# 		if values.get("user") == "":
# 			raise Warning(_('type field cannot be empty.'))
#
# 		if values.get("code"):
# 			s = str(values.get("code"))
# 			code_no = s.rstrip('0').rstrip('.') if '.' in s else s
#
# 		account_obj = self.env['account.account']
# 		account_search = account_obj.search([
# 			('code', '=', values.get('code'))
# 			])
#
# 		is_reconcile = False
# 		is_deprecated= False
#
# 		if values.get("reconcile") == 'TRUE' or values.get("reconcile") == "1":
# 			is_reconcile = True
#
# 		if values.get("deprecat") == 'TRUE'  or values.get("deprecat") == "1":
# 			is_deprecated = True
#
# 		user_id = self.find_user_type(values.get('user'))
# 		currency_get = self.find_currency(values.get('currency'))
# 		# tag_ids = self.find_tags(values.get('tag'))
# 		group_get = self.find_group(values.get('group'))
#
# # --------tax-
# 		tax_ids = []
# 		if values.get('tax'):
# 			if ';' in  values.get('tax'):
# 				tax_names = values.get('tax').split(';')
# 				for name in tax_names:
# 					tax= self.env['account.tax'].search([('name', '=', name)])
# 					if not tax:
# 						raise Warning(_('%s Tax not in your system') % name)
# 					for t in tax:
# 						tax_ids.append(t)
#
# 			elif ',' in  values.get('tax'):
# 				tax_names = values.get('tax').split(',')
# 				for name in tax_names:
# 					tax= self.env['account.tax'].search([('name', '=', name)])
# 					if not tax:
# 						raise Warning(_('%s Tax not in your system') % name)
# 					for t in tax:
# 						tax_ids.append(t)
# 			else:
# 				tax_names = values.get('tax').split(',')
# 				tax= self.env['account.tax'].search([('name', '=', tax_names)])
# 				if not tax:
# 					raise Warning(_('"%s" Tax not in your system') % tax_names)
# 				for t in tax:
# 					tax_ids.append(t)
#
# # ------------tags
# 		tag_ids = []
# 		if values.get('tag'):
# 			if ';' in  values.get('tag'):
# 				tag_names = values.get('tag').split(';')
# 				for name in tag_names:
# 					tag= self.env['account.account.tag'].search([('name', '=', name)])
# 					if not tag:
# 						raise Warning(_('"%s" Tag not in your system') % name)
# 					tag_ids.append(tag)
#
# 			elif ',' in  values.get('tag'):
# 				tag_names = values.get('tag').split(',')
# 				for name in tag_names:
# 					tag= self.env['account.account.tag'].search([('name', '=', name)])
# 					if not tag:
# 						raise Warning(_('"%s" Tag not in your system') % name)
# 					tag_ids.append(tag)
# 			else:
# 				tag_names = values.get('tag').split(',')
# 				tag= self.env['account.account.tag'].search([('name', '=', tag_names)])
# 				if not tag:
# 					raise Warning(_('"%s" Tag not in your system') % tag_names)
# 				tag_ids.append(tag)
#
# 		data={
# 				'code' : code_no,
# 				'name' : values.get('name'),
# 				'user_type_id':user_id.id,
# 				'tax_ids':[(6,0,[y.id for y in tax_ids])]if values.get('tax') else False,
# 				'tag_ids':[(6,0,[x.id for x in tag_ids])]if values.get('tag') else False,
# 				'group_id':group_get.id,
# 				'currency_id':currency_get or False,
# 				'reconcile':is_reconcile,
# 				'deprecated':is_deprecated,
#
# 				}
# 		chart_id = account_obj.create(data)
#
# 		return chart_id
#
# # ---------------------------user-----------------
#
#
# 	def find_user_type(self,user):
# 		user_type=self.env['account.account.type']
# 		user_search = user_type.search([('name','=',user)])
# 		if user_search:
# 			return user_search
# 		else:
# 			raise Warning(_('Field User is not correctly set.'))
#
# # --------------------currency------------------
#
#
# 	def find_currency(self, name):
# 		currency_obj = self.env['res.currency']
# 		currency_search = currency_obj.search([('name', '=', name)])
# 		if currency_search:
# 			return currency_search.id
# 		else:
# 			if name == "":
# 				pass
# 			else:
# 				raise Warning(_(' %s currency are not available.') % name)
#
# # -----------------group-------
#
#
# 	def find_group(self,group):
# 		group_type=self.env['account.group']
# 		group_search = group_type.search([('name','=',group)])
#
# 		if group_search:
# 			return group_search
# 		else:
# 			group_id = group_type.create({
# 				'name' : group
# 				})
# 			return group_id
