odoo.define("documents_spreadsheet_relation.KanbanController", function (require) {
    "use strict";
    var KanbanController = require("documents.DocumentsKanbanController");
    var core = require("web.core");
    var _t = core._t;
    KanbanController.include({
        renderButtons: function () {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                this.$buttons.append(
                    '<button class="btn btn-secondary o_spreadsheet_relation_button" type="button">Configurar relación</button>'
                );
                this.$buttons.on(
                    "click",
                    ".o_spreadsheet_relation_button",
                    this._onSpreadsheetRelationButtonClick.bind(this)
                );
            }
        },
        _onSpreadsheetRelationButtonClick: function () {
            var selectedRecords = this.getSelectedRecords();
            if (selectedRecords.length === 1) {
                this.do_action({
                    type: "ir.actions.act_window",
                    res_model: "spreadsheet.relation.wizard",
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        default_document_id: selectedRecords[0].res_id,
                    },
                });
            } else {
                this.do_warn(
                    _t("Selección de documentos"),
                    _t("Por favor, seleccione un solo documento.")
                );
            }
        },
    });
});
