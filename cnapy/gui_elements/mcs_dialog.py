"""The dialog for calculating minimal cut sets"""

import io
import traceback
import scipy

from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QCompleter,
                            QDialog, QGroupBox, QHBoxLayout, QHeaderView,
                            QLabel, QLineEdit, QMessageBox, QPushButton,
                            QRadioButton, QTableWidget, QVBoxLayout)
import optlang_enumerator.mcs_computation as mcs_computation
import cobra
from cobra.util.solver import interface_to_str
from cnapy.appdata import AppData
import cnapy.utils as utils
from cnapy.flux_vector_container import FluxVectorContainer


class MCSDialog(QDialog):
    """A dialog to perform minimal cut set computation"""

    def __init__(self, appdata: AppData, central_widget):
        QDialog.__init__(self)
        self.setWindowTitle("Minimal Cut Sets Computation")

        self.appdata = appdata
        self.central_widget = central_widget
        self.out = io.StringIO()
        self.err = io.StringIO()

        self.layout = QVBoxLayout()
        l1 = QLabel("Target Region(s)")
        self.layout.addWidget(l1)
        s1 = QHBoxLayout()

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        self.target_list = QTableWidget(1, 4)
        self.target_list.setHorizontalHeaderLabels(
            ["region no", "T", "≥/≤", "t"])
        self.target_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.target_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.target_list.horizontalHeader().resizeSection(0, 100)
        self.target_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.target_list.horizontalHeader().resizeSection(2, 50)
        item = QLineEdit("1")
        self.target_list.setCellWidget(0, 0, item)
        item2 = ReceiverLineEdit(self)
        item2.setCompleter(completer)
        self.target_list.setCellWidget(0, 1, item2)
        combo = QComboBox(self.target_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.target_list.setCellWidget(0, 2, combo)
        item = QLineEdit("0")
        self.target_list.setCellWidget(0, 3, item)
        self.active_receiver = item2

        s1.addWidget(self.target_list)

        s11 = QVBoxLayout()
        self.add_target = QPushButton("+")
        self.add_target.clicked.connect(self.add_target_region)
        self.rem_target = QPushButton("-")
        self.rem_target.clicked.connect(self.rem_target_region)
        s11.addWidget(self.add_target)
        s11.addWidget(self.rem_target)
        s1.addItem(s11)
        self.layout.addItem(s1)

        l2 = QLabel("Desired Region(s)")
        self.layout.addWidget(l2)
        s2 = QHBoxLayout()
        self.desired_list = QTableWidget(1, 4)
        self.desired_list.setHorizontalHeaderLabels(
            ["region no", "D", "≥/≤", "d"])
        self.desired_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.desired_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.desired_list.horizontalHeader().resizeSection(0, 100)
        self.desired_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.desired_list.horizontalHeader().resizeSection(2, 50)
        item = QLineEdit("1")
        self.desired_list.setCellWidget(0, 0, item)
        item2 = ReceiverLineEdit(self)
        item2.setCompleter(completer)
        self.desired_list.setCellWidget(0, 1, item2)
        combo = QComboBox(self.desired_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.desired_list.setCellWidget(0, 2, combo)
        item = QLineEdit("0")
        self.desired_list.setCellWidget(0, 3, item)
        s2.addWidget(self.desired_list)

        s21 = QVBoxLayout()
        self.add_desire = QPushButton("+")
        self.add_desire.clicked.connect(self.add_desired_region)
        self.rem_desire = QPushButton("-")
        self.rem_desire.clicked.connect(self.rem_desired_region)
        s21.addWidget(self.add_desire)
        s21.addWidget(self.rem_desire)
        s2.addItem(s21)
        self.layout.addItem(s2)

        s3 = QHBoxLayout()

        sgx = QVBoxLayout()
        self.exclude_boundary = QCheckBox(
            "Exclude boundary\nreactions as cuts")
        sg1 = QHBoxLayout()
        s31 = QVBoxLayout()
        l = QLabel("Max. Solutions")
        s31.addWidget(l)
        l = QLabel("Max. Size")
        s31.addWidget(l)
        l = QLabel("Time Limit [sec]")
        s31.addWidget(l)

        sg1.addItem(s31)

        s32 = QVBoxLayout()
        self.max_solu = QLineEdit("inf")
        self.max_solu.setMaximumWidth(50)
        s32.addWidget(self.max_solu)
        self.max_size = QLineEdit("7")
        self.max_size.setMaximumWidth(50)
        s32.addWidget(self.max_size)
        self.time_limit = QLineEdit("inf")
        self.time_limit.setMaximumWidth(50)
        s32.addWidget(self.time_limit)

        sg1.addItem(s32)
        sgx.addWidget(self.exclude_boundary)
        sgx.addItem(sg1)
        s3.addItem(sgx)

        g3 = QGroupBox("Current solver")
        s33 = QVBoxLayout()
        self.solver_optlang = QLabel()
        self.set_optlang_solver_text()
        self.solver_optlang.setToolTip(
            "Change solver in COBRApy configuration.")
        s33.addWidget(self.solver_optlang)
        g3.setLayout(s33)
        s3.addWidget(g3)

        g4 = QGroupBox("MCS search")
        s34 = QVBoxLayout()
        self.bg2 = QButtonGroup()
        self.any_mcs = QRadioButton("any MCS (fast)")
        self.any_mcs.setChecked(True)
        s34.addWidget(self.any_mcs)
        self.bg2.addButton(self.any_mcs)

        # Search type: by cardinality only with CPLEX/Gurobi possible
        self.mcs_by_cardinality = QRadioButton("by cardinality")
        s34.addWidget(self.mcs_by_cardinality)
        self.bg2.addButton(self.mcs_by_cardinality)

        self.smalles_mcs_first = QRadioButton("smallest MCS first")
        s34.addWidget(self.smalles_mcs_first)
        self.bg2.addButton(self.smalles_mcs_first)

        # Search type: continuous search only with optlang + CPLEX/Gurobi possible
        self.mcs_continuous_search = QRadioButton("continuous search")
        s34.addWidget(self.mcs_continuous_search)
        self.bg2.addButton(self.mcs_continuous_search)
        g4.setLayout(s34)

        s3.addWidget(g4)
        self.layout.addItem(s3)

        self.configure_solver_options()

        s4 = QVBoxLayout()
        self.consider_scenario = QCheckBox(
            "Consider constraint given by scenario")
        s4.addWidget(self.consider_scenario)
        self.layout.addItem(s4)

        buttons = QHBoxLayout()
        self.compute_mcs = QPushButton("Compute MCS")
        buttons.addWidget(self.compute_mcs)
        self.cancel = QPushButton("Close")
        buttons.addWidget(self.cancel)
        self.layout.addItem(buttons)

        # max width for buttons
        self.add_target.setMaximumWidth(20)
        self.rem_target.setMaximumWidth(20)
        self.add_desire.setMaximumWidth(20)
        self.rem_desire.setMaximumWidth(20)

        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.compute_mcs.clicked.connect(self.compute)

        self.central_widget.broadcastReactionID.connect(self.receive_input)

    @Slot(str)
    def receive_input(self, text):
        completer_mode = self.active_receiver.completer().completionMode()
        # temporarily disable completer popup
        self.active_receiver.completer().setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self.active_receiver.insert(text)
        self.active_receiver.completer().setCompletionMode(completer_mode)

    @Slot()
    def set_optlang_solver_text(self):
        self.optlang_solver_name = interface_to_str(self.appdata.project.cobra_py_model.problem)
        self.solver_optlang.setText(f"{self.optlang_solver_name} (optlang)")

    @Slot()
    def configure_solver_options(self):  # called when switching solver
        self.exclude_boundary.setEnabled(True)
        if self.optlang_solver_name != 'cplex' and self.optlang_solver_name != 'gurobi':
            if self.mcs_by_cardinality.isChecked() or self.mcs_continuous_search.isChecked():
                self.any_mcs.setChecked(True)
            self.mcs_by_cardinality.setEnabled(False)
            self.mcs_continuous_search.setEnabled(False)
        else:
            self.mcs_by_cardinality.setEnabled(True)
            self.mcs_continuous_search.setEnabled(True)


    def add_target_region(self):
        i = self.target_list.rowCount()
        self.target_list.insertRow(i)

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        item = QLineEdit("1")
        self.target_list.setCellWidget(i, 0, item)
        item2 = ReceiverLineEdit(self)
        item2.setCompleter(completer)
        self.target_list.setCellWidget(i, 1, item2)
        combo = QComboBox(self.target_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.target_list.setCellWidget(i, 2, combo)
        item = QLineEdit("0")
        self.target_list.setCellWidget(i, 3, item)

    def add_desired_region(self):
        i = self.desired_list.rowCount()
        self.desired_list.insertRow(i)

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        item = QLineEdit("1")
        self.desired_list.setCellWidget(i, 0, item)
        item2 = ReceiverLineEdit(self)
        item2.setCompleter(completer)
        self.desired_list.setCellWidget(i, 1, item2)
        combo = QComboBox(self.desired_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.desired_list.setCellWidget(i, 2, combo)
        item = QLineEdit("0")
        self.desired_list.setCellWidget(i, 3, item)

    def rem_target_region(self):
        i = self.target_list.rowCount()
        self.target_list.removeRow(i-1)

    def rem_desired_region(self):
        i = self.desired_list.rowCount()
        self.desired_list.removeRow(i-1)

    def compute(self):
        mcs_equation_errors = self.check_for_mcs_equation_errors()
        if mcs_equation_errors == "":
            self.compute_optlang()
        else:
            QMessageBox.warning(
                self,
                "MCS target/desired region error",
                f"Cannot perform MCS calculation due to the following error(s) "
                f"in the given target and/or desired regions:\n"
                f"{mcs_equation_errors}"
            )


    def compute_optlang(self):
        max_mcs_num = float(self.max_solu.text())
        max_mcs_size = int(self.max_size.text())
        timeout = float(self.time_limit.text())
        if timeout == float('inf'):
            timeout = None

        if self.smalles_mcs_first.isChecked():
            enum_method = 1
        elif self.mcs_by_cardinality.isChecked():
            enum_method = 2
        elif self.any_mcs.isChecked():
            enum_method = 3
        elif self.mcs_continuous_search.isChecked():
            enum_method = 4

        with self.appdata.project.cobra_py_model as model:
            update_stoichiometry_hash = False
            if self.consider_scenario.isChecked():  # integrate scenario into model bounds
                self.appdata.project.load_scenario_into_model(model)
                if len(self.appdata.project.scen_values) > 0:
                    update_stoichiometry_hash = True
            for r in model.reactions:  # make all reactions bounded for COBRApy FVA
                if r.lower_bound == -float('inf'):
                    r.lower_bound = cobra.Configuration().lower_bound
                    r.set_hash_value()
                    update_stoichiometry_hash = True
                if r.upper_bound == float('inf'):
                    r.upper_bound = cobra.Configuration().upper_bound
                    r.set_hash_value()
                    update_stoichiometry_hash = True
            if self.appdata.use_results_cache and update_stoichiometry_hash:
                model.set_stoichiometry_hash_object()
            reac_id = model.reactions.list_attr("id")
            reac_id_symbols = mcs_computation.get_reac_id_symbols(reac_id)
            rows = self.target_list.rowCount()
            targets = dict()
            for i in range(0, rows):
                p1 = self.target_list.cellWidget(i, 0).text()
                p2 = self.target_list.cellWidget(i, 1).text()
                if len(p1) > 0 and len(p2) > 0:
                    if self.target_list.cellWidget(i, 2).currentText() == '≤':
                        p3 = "<="
                    else:
                        p3 = ">="
                    p4 = float(self.target_list.cellWidget(i, 3).text())
                    targets.setdefault(p1, []).append((p2, p3, p4))
            targets = list(targets.values())
            try:
                targets = [mcs_computation.relations2leq_matrix(mcs_computation.parse_relations(
                    t, reac_id_symbols=reac_id_symbols), reac_id) for t in targets]
            except ValueError:
                QMessageBox.warning(self, "Failed to parse the target region(s)",
                                    "Check that the equations are correct.")
                return

            rows = self.desired_list.rowCount()
            desired = dict()
            for i in range(0, rows):
                p1 = self.desired_list.cellWidget(i, 0).text()
                p2 = self.desired_list.cellWidget(i, 1).text()
                if len(p1) > 0 and len(p2) > 0:
                    if self.desired_list.cellWidget(i, 2).currentText() == '≤':
                        p3 = "<="
                    else:
                        p3 = ">="
                    p4 = float(self.desired_list.cellWidget(i, 3).text())
                    desired.setdefault(p1, []).append((p2, p3, p4))
            desired = list(desired.values())
            try:
                desired = [mcs_computation.relations2leq_matrix(mcs_computation.parse_relations(
                    d, reac_id_symbols=reac_id_symbols), reac_id) for d in desired]
            except ValueError:
                QMessageBox.warning(self, "Failed to parse the desired region(s)",
                                    "Check that the equations are correct.")
                return

            self.setCursor(Qt.BusyCursor)
            try:
                mcs, err_val = mcs_computation.compute_mcs(model,
                                targets=targets, desired=desired, enum_method=enum_method,
                                max_mcs_size=max_mcs_size, max_mcs_num=max_mcs_num, timeout=timeout,
                                exclude_boundary_reactions_as_cuts=self.exclude_boundary.isChecked(),
                                results_cache_dir=self.appdata.results_cache_dir
                                if self.appdata.use_results_cache else None)
            except mcs_computation.InfeasibleRegion as e:
                QMessageBox.warning(self, 'Cannot calculate MCS', str(e))
                return targets, desired
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                utils.show_unknown_error_box(exstr)
                return targets, desired
            finally:
                self.setCursor(Qt.ArrowCursor)

        print(err_val)
        if err_val == 1:
            QMessageBox.warning(self, "Enumeration stopped abnormally",
                                "Result is probably incomplete.\nCheck console output for more information.")
        elif err_val == -1:
            QMessageBox.warning(self, "Enumeration terminated permaturely",
                                "Aborted due to excessive generation of candidates that are not cut sets.\n"
                                "Modify the problem or try a different enumeration setup.")

        if len(mcs) == 0:
            QMessageBox.information(self, 'No cut sets',
                                          'Cut sets have not been calculated or do not exist.')
            return targets, desired

        # omcs = [{reac_id[i]: -1.0 for i in m} for m in mcs]
        omcs = scipy.sparse.lil_matrix((len(mcs), len(reac_id)))
        for i,m in enumerate(mcs):
            for j in m:
                omcs[i, j] = -1.0
        self.appdata.project.modes = FluxVectorContainer(omcs, reac_id=reac_id)
        self.central_widget.mode_navigator.current = 0
        QMessageBox.information(self, 'Cut sets found',
                                      str(len(mcs))+' Cut sets have been calculated.')

        self.central_widget.mode_navigator.set_to_mcs()
        self.central_widget.update_mode()
        self.accept()

    def check_left_mcs_equation(self, equation: str) -> str:
        errors = ""

        semantics = []
        reaction_ids = []
        last_part = ""
        counter = 1
        for char in equation+" ":
            if (char == " ") or (char in ("*", "/", "+", "-")) or (counter == len(equation+" ")):
                if last_part != "":
                    try:
                        float(last_part)
                    except ValueError:
                        reaction_ids.append(last_part)
                        semantics.append("reaction")
                    else:
                        semantics.append("number")
                    last_part = ""

                if counter == len(equation+" "):
                    break

            if char in "*":
                semantics.append("multiplication")
            elif char in "/":
                semantics.append("division")
            elif char in ("+", "-"):
                semantics.append("dash")
            elif char not in " ":
                last_part += char
            counter += 1

        if len(reaction_ids) == 0:
            errors += f"EQUATION ERROR in {equation}:\nNo reaction ID is given in the equation\n"

        if semantics.count("division") > 1:
            errors += f"ERROR in {equation}:\nAn equation must not have more than one /"

        last_is_multiplication = False
        last_is_division = False
        last_is_dash = False
        last_is_reaction = False
        prelast_is_reaction = False
        prelast_is_dash = False
        last_is_number = False
        is_start = True
        for semantic in semantics:
            if is_start:
                if semantic in ("multiplication", "division"):
                    errors += f"ERROR in {equation}:\nAn equation must not start with * or /"
                is_start = False

            if (last_is_multiplication or last_is_division) and (semantic in ("multiplication", "division")):
                errors += f"ERROR in {equation}:\n* or / must not follow on * or /\n"
            if last_is_dash and (semantic in ("multiplication", "division")):
                errors += f"ERROR in {equation}:\n* or / must not follow on + or -\n"
            if last_is_number and (semantic == "reaction"):
                errors += f"ERROR in {equation}:\nA reaction must not directly follow on a number without a mathematical operation\n"
            if last_is_reaction and (semantic == "reaction"):
                errors += f"ERROR in {equation}:\nA reaction must not follow on a reaction ID\n"
            if last_is_number and (semantic == "number"):
                errors += f"ERROR in {equation}:\nA number must not follow on a number ID\n"

            if prelast_is_reaction and last_is_multiplication and (semantic == "reaction"):
                errors += f"ERROR in {equation}:\nTwo reactions must not be multiplied together\n"

            if last_is_reaction:
                prelast_is_reaction = True
            else:
                prelast_is_reaction = False

            if last_is_dash:
                prelast_is_dash = True
            else:
                prelast_is_dash = False

            last_is_multiplication = False
            last_is_division = False
            last_is_dash = False
            last_is_reaction = False
            last_is_number = False
            if semantic == "multiplication":
                last_is_multiplication = True
            elif semantic == "division":
                last_is_division = True
            elif semantic == "reaction":
                last_is_reaction = True
            elif semantic == "dash":
                last_is_dash = True
            elif semantic == "number":
                last_is_number = True

        if last_is_dash or last_is_multiplication or last_is_division:
            errors += (f"ERROR in {equation}:\nA reaction must not end "
                       f"with a +, -, * or /")

        if prelast_is_dash and last_is_number:
            errors += (f"ERROR in {equation}:\nA reaction must not end "
                       f"with a separated number term only")

        with self.appdata.project.cobra_py_model as model:
            model_reaction_ids = [x.id for x in model.reactions]
            for reaction_id in reaction_ids:
                if reaction_id not in model_reaction_ids:
                    errors += (f"ERROR in {equation}:\nA reaction with "
                               f"the ID {reaction_id} does not exist in the model\n")

        return errors


    def check_right_mcs_equation(self, equation: str) -> str:
        try:
            float(equation)
        except ValueError:
            error = f"ERROR in {equation}:\nRight equation must be a number\n"
            return error
        else:
            return ""

    def check_for_mcs_equation_errors(self) -> str:
        errors = ""
        rows = self.target_list.rowCount()
        for i in range(0, rows):
            target_left = self.target_list.cellWidget(i, 1).text()
            errors += self.check_left_mcs_equation(target_left)
            target_right = self.target_list.cellWidget(i, 3).text()
            errors += self.check_right_mcs_equation(target_right)

        rows = self.desired_list.rowCount()
        for i in range(0, rows):
            desired_left = self.desired_list.cellWidget(i, 1).text()
            if len(desired_left) > 0:
                errors += self.check_left_mcs_equation(desired_left)

            desired_right = self.desired_list.cellWidget(i, 3).text()
            if len(desired_right) > 0:
                errors += self.check_right_mcs_equation(desired_right)

        return errors

class ReceiverLineEdit(QLineEdit):
    def __init__(self, mcs_dialog):
        super().__init__()
        self.mcs_dialog = mcs_dialog

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.mcs_dialog.active_receiver = self
