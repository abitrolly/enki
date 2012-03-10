"""
searchwidget --- Search widget and controler
============================================

Module implements search widget and manages search and replace operations
"""

import os.path
import re

from PyQt4 import uic
from PyQt4.QtCore import QDir, QEvent, \
                         QRect, QSize, Qt

from PyQt4.QtGui import QCompleter, QDirModel, QFileDialog,  \
                        QFrame, QFileDialog, QIcon, \
                        QMessageBox, \
                        QPainter,  \
                        QPalette, \
                        QProgressBar, QToolButton, QWidget

from mks.core.core import core

from mks.plugins.searchreplace import *
import searchresultsmodel

class SearchContext:
    """Structure holds parameters of search or replace operation in progress
    """    
    def __init__(self, regExp, replaceText, searchPath, mode):
        self.mask = []
        self.openedFiles = {}
        self.regExp = regExp
        self.replaceText = replaceText
        self.searchPath = searchPath
        self.mode = mode
        self.encoding = 'utf_8'

class SearchWidget(QFrame):
    """Widget, appeared, when Ctrl+F pressed.
    Has different forms for different search modes
    """

    Normal = 'normal'
    Good = 'good'
    Bad = 'bad'
    Incorrect = 'incorrect'

    def __init__(self, plugin):
        QFrame.__init__(self, core.workspace())
        self._mode = None
        self.plugin = plugin
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'SearchWidget.ui'), self)
        
        self.cbSearch.completer().setCaseSensitivity( Qt.CaseSensitive )
        self.cbReplace.completer().setCaseSensitivity( Qt.CaseSensitive )
        self.fsModel = QDirModel(self.cbPath.lineEdit())
        self.fsModel.setFilter( QDir.AllDirs | QDir.NoDotAndDotDot )
        self.cbPath.lineEdit().setCompleter(QCompleter(self.fsModel,
                                                       self.cbPath.lineEdit() ))
        # TODO QDirModel is deprecated but QCompleter does not yet handle
        # QFileSystemodel - please update when possible."""
        self.cbMask.completer().setCaseSensitivity( Qt.CaseSensitive )
        self.pbSearchStop.setVisible( False )
        self.pbReplaceCheckedStop.setVisible( False )
        
        self._progress = QProgressBar( self )
        self._progress.setAlignment( Qt.AlignCenter )
        self._progress.setToolTip( self.tr( "Search in progress..." ) )
        self._progress.setMaximumSize( QSize( 80, 16 ) )
        core.mainWindow().statusBar().insertPermanentWidget( 0, self._progress )
        self._progress.setVisible( False )
        
        # threads
        from threads import SearchThread, ReplaceThread  # TODO why it is created here???
        self.searchThread = SearchThread()
        self._replaceThread = ReplaceThread()

        self._dock = None
        
        # mode actions
        self.tbMode = QToolButton( self.cbSearch.lineEdit() )
        self.tbMode.setIcon( QIcon( ":/mksicons/misc.png" ) )
        self.tbMode.setPopupMode( QToolButton.InstantPopup )
        self.tbMode.setMenu( core.actionManager().\
                action( "mNavigation/mSearchReplace" ).menu() )
        self.tbMode.setCursor( Qt.ArrowCursor )
        self.tbMode.installEventFilter( self )
        
        # cd up action
        self.tbCdUp = QToolButton( self.cbPath.lineEdit() )
        self.tbCdUp.setIcon( QIcon( ":/mksicons/go-up.png" ) )
        self.tbCdUp.setCursor( Qt.ArrowCursor )
        self.tbCdUp.installEventFilter( self )

        QWidget.setTabOrder(self.cbSearch, self.cbReplace)
        QWidget.setTabOrder(self.cbReplace, self.cbPath)
        
        #TODO PasNox, check if we need this on Mac
        # mac
        #pMonkeyStudio.showMacFocusRect( self, False, True )
        #pMonkeyStudio.setMacSmallSize( self, True, True )
        #ifdef Q_OS_MAC
        # QSize size( 12, 12 )
        #
        #foreach ( QAbstractButton* button, findChildren<QAbstractButton*>() )
        #    button.setIconSize( size )
        #    button.setFixedHeight( 24 )
        #vlMain.setSpacing( 0 )
        #endif
        
        # TODO mask tooltip
        #languages = pMonkeyStudio.availableLanguages()
        #
        #for ( i = 0; i < languages.count(); i += 10 )
        #    languages[ i ].prepend( "\n" )
        #maskToolTip = self.tr( "Space separated list of wildcards, *.h *.cpp 
        #file???.txt\n"
        #"You can use language name too so the search will only apply to 
        #the language suffixes.\n"
        #"Available languages: %1" ).arg( languages.join( ", " ) )
        # self.cbMask.setToolTip( maskToolTip )
        
        
        #TODO support encodings
        #falsePositives = set(["aliases"])
        #foundCodecs = set(name for imp, name, ispkg in \
        #                pkgutil.iter_modules(encodings.__path__) if not ispkg)
        #foundCodecs.difference_update(falsePositives)
        #foundCodecs = sorted(list(foundCodecs))
        #self.cbEncoding.addItems(foundCodecs)
        #self.cbEncoding.setCurrentIndex(foundCodecs.index('utf_8'))
        #self.cbEncoding.setCurrentIndex( 
        #    self.cbEncoding.findText( pMonkeyStudio.defaultCodec() ) )

        # connections
        self.cbSearch.lineEdit().textChanged.connect(self._updateActionsState)
        self.cbRegularExpression.stateChanged.connect(self._updateActionsState)
        self.cbCaseSensitive.stateChanged.connect(self._updateActionsState)
        
        self.cbSearch.lineEdit().textChanged.connect(self._onSearchRegExpChanged)
        self.cbRegularExpression.stateChanged.connect(self._onSearchRegExpChanged)
        self.cbCaseSensitive.stateChanged.connect(self._onSearchRegExpChanged)
        
        core.workspace().currentDocumentChanged.connect(self._updateActionsState)
        
        self.tbCdUp.clicked.connect(self.cdUp_pressed)
        self.searchThread.started.connect(self.searchThread_stateChanged)
        self.searchThread.finished.connect(self.searchThread_stateChanged)
        self.searchThread.progressChanged.connect(\
                                        self.searchThread_progressChanged)
        self._replaceThread.started.connect(self.replaceThread_stateChanged)
        self._replaceThread.finished.connect(self.replaceThread_stateChanged)
        self._replaceThread.openedFileHandled.connect(\
                                        self.replaceThread_openedFileHandled)
        self._replaceThread.error.connect(self.replaceThread_error)
        
        core.actionManager().action("mNavigation/mSearchReplace/aSearchNext")\
                                        .triggered.connect(self.on_pbNext_pressed)
        core.actionManager().action("mNavigation/mSearchReplace/aSearchPrevious")\
                                        .triggered.connect(self.on_pbPrevious_pressed)
        
        self._updateActionsState()
        
        core.mainWindow().hideAllWindows.connect(self.hide)

        self._defaultBackgroundColor = self.cbSearch.palette().color(QPalette.Base)

    def setResultsDock(self, dock ):
        """Set to widget pointer to the search results dock
        """
        self._dock = dock

        # connections
        self._replaceThread.resultsHandled.connect(\
                                    self._dock.onResultsHandledByReplaceThread)

    def setMode(self, mode ):
        """Change search mode.
        i.e. from "Search file" to "Replace directory"
        """
        if self._mode == mode and \
           self.isVisible() and \
           not core.workspace().currentDocument().hasFocus():
            self.cbSearch.lineEdit().selectAll()
            self.cbSearch.setFocus()
            return
        
        self.searchThread.stop()
        self._replaceThread.stop()
        
        currentDocumentOnly = False
        
        # clear search results if needed.

        if mode & ModeFlagFile:
            currentDocumentOnly = True
        else:
            currentDocumentOnly = False
            self.searchThread.clear()
        
        self._mode = mode
        
        # TODO support search in project
        #if self._mode & ModeFlagProjectFiles :
        #    if  self.searchContext.project :
        #        encoding = self.searchContext.project.temporaryValue(
        #        "encoding", mks.monkeystudio.defaultCodec() ).toString()
        #        self.searchContext.encoding = encoding
        #        self.cbEncoding.setCurrentIndex( self.cbEncoding.findText(
        #        encoding ) )
        #assert( self.searchContext.encoding )
        
        if core.workspace().currentDocument():
            searchText = core.workspace().currentDocument().selectedText()
        else:
            searchText = ''
        
        self.setVisible( mode != ModeNo )

        if searchText:
            self.cbSearch.setEditText( searchText )
            self.cbReplace.setEditText( searchText )
            
        if  mode & ModeFlagDirectory :
            try:
                searchPath = os.path.abspath(unicode(os.path.curdir))
                self.cbPath.setEditText( searchPath )
            except OSError:  # current directory might be deleted
                pass 

        self.cbSearch.setFocus()
        self.cbSearch.lineEdit().selectAll()

        # hlamer: I'm sory for long lines, but, even workse without it
        # Set widgets visibility flag according to state
        widgets = (self.wSearch, self.pbPrevious, self.pbNext, self.pbSearch, self.wReplace, self.wPath, \
                   self.pbReplace, self.pbReplaceAll, self.pbReplaceChecked, self.wOptions, self.wMask, self.wEncoding,)
        #                             wSear  pbPrev pbNext pbSear wRepl  wPath  pbRep  pbRAll pbRCHK wOpti wMask wEnc
        visible = \
        {ModeNo     :             (0,     0,     0,     0,     0,     0,     0,     0,     0,    0,    0,    0,),
         ModeSearch :             (1,     1,     1,     0,     0,     0,     0,     1,     1,    1,    0,    0,),
         ModeReplace:             (1,     1,     1,     0,     1,     0,     1,     1,     0,    1,    0,    0,),
         ModeSearchDirectory:     (1,     0,     0,     1,     0,     1,     0,     0,     0,    1,    1,    1,),
         ModeReplaceDirectory:    (1,     0,     0,     1,     1,     1,     0,     0,     1,    1,    1,    1,),
         ModeSearchProjectFiles:  (1,     0,     0,     1,     0,     0,     0,     0,     0,    1,    1,    1,),
         ModeSearchProjectFiles:  (1,     0,     0,     1,     0,     0,     0,     0,     0,    1,    1,    1,),
         ModeReplaceProjectFiles: (1,     0,     0,     1,     1,     0,     0,     0,     1,    1,    1,    1,),
         ModeSearchOpenedFiles:   (1,     0,     0,     1,     0,     0,     0,     0,     0,    1,    1,    0,),
         ModeReplaceOpenedFiles:  (1,     0,     0,     1,     1,     0,     0,     0,     1,    1,    1,    0,)}
        
        for i, widget in enumerate(widgets):
            widget.setVisible(visible[mode][i])

        self.updateLabels()
        self.updateWidgets()

    def eventFilter(self, object_, event ):
        """ Event filter for mode switch tool button
        Draws icons in the search and path lineEdits
        """
        if  event.type() == QEvent.Paint :
            toolButton = object_
            if toolButton == self.tbMode:
                lineEdit = self.cbSearch.lineEdit()
            else:
                lineEdit = self.cbPath.lineEdit()
            lineEdit.setContentsMargins( lineEdit.height(), 0, 0, 0 )
            
            height = lineEdit.height()
            availableRect = QRect( 0, 0, height, height )
            
            if  toolButton.rect() != availableRect :
                toolButton.setGeometry( availableRect )
            
            painter = QPainter ( toolButton )
            toolButton.icon().paint( painter, availableRect )
            
            return True

        return QFrame.eventFilter( self, object_, event )

    def keyPressEvent(self, event ):
        """Handles ESC and ENTER pressings on widget for hide widget or start action"""
        if  event.modifiers() == Qt.NoModifier :
            if event.key() == Qt.Key_Escape:
                core.workspace().focusCurrentDocument()
                self.hide()
            elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
                if self._mode == ModeNo:
                    pass
                elif self._mode == ModeSearch:
                    self.pbNext.click()
                elif self._mode in (ModeSearchDirectory, \
                                    ModeSearchProjectFiles, \
                                    ModeSearchOpenedFiles, \
                                    ModeReplaceDirectory, \
                                    ModeReplaceProjectFiles, \
                                    ModeReplaceOpenedFiles):
                    if not self.searchThread.isRunning():
                        self.pbSearch.click()
                    else:
                        self.pbSearchStop.click()
                elif self._mode == ModeReplace:
                    self.pbReplace.click()

        QFrame.keyPressEvent( self, event )

    def updateLabels(self):
        """Update 'Search' 'Replace' 'Path' labels geometry
        """
        width = 0

        if  self.lSearch.isVisible() :
            width = max( width, self.lSearch.minimumSizeHint().width() )

        if   self.lReplace.isVisible() :
            width = max( width,  self.lReplace.minimumSizeHint().width() )

        if  self.lPath.isVisible() :
            width = max( width, self.lPath.minimumSizeHint().width() )

        self.lSearch.setMinimumWidth( width )
        self.lReplace.setMinimumWidth( width )
        self.lPath.setMinimumWidth( width )


    def updateWidgets(self):
        """Update geometry of widgets with buttons
        """
        width = 0

        if  self.wSearchRight.isVisible() :
            width = max( width, self.wSearchRight.minimumSizeHint().width() )

        if  self.wReplaceRight.isVisible() :
            width = max( width, self.wReplaceRight.minimumSizeHint().width() )

        if  self.wPathRight.isVisible() :
            width = max( width, self.wPathRight.minimumSizeHint().width() )

        self.wSearchRight.setMinimumWidth( width )
        self.wReplaceRight.setMinimumWidth( width )
        self.wPathRight.setMinimumWidth( width )

    def updateComboBoxes(self):
        """Update comboboxes with last used texts
        """
        searchText = self.cbSearch.currentText()
        replaceText = self.cbReplace.currentText()
        maskText = self.cbMask.currentText()
        
        # search
        if searchText:
            index = self.cbSearch.findText( searchText )
            
            if  index == -1 :
                self.cbSearch.addItem( searchText )
        
        # replace
        if replaceText:
            index = self.cbReplace.findText( replaceText )
            
            if  index == -1 :
                self.cbReplace.addItem( replaceText )

        # mask
        if maskText:
            index = self.cbMask.findText( maskText )
            
            if  index == -1 :
                self.cbMask.addItem( maskText )
    
    def _searchPatternTextAndFlags(self):
        """Get search pattern and flags
        """
        pattern = self.cbSearch.currentText()
        if not self.cbRegularExpression.checkState() == Qt.Checked:
            pattern = re.escape(pattern)
        flags = 0
        if not self.cbCaseSensitive.checkState() == Qt.Checked:
            flags = re.IGNORECASE
        return pattern, flags

    def _getRegExp(self):
        """Read search parameters from controls and present it as a regular expression
        """
        pattern, flags = self._searchPatternTextAndFlags()
        return re.compile(pattern, flags)
    
    def _isSearchRegExpValid(self):
        """Try to compile search pattern to check if it is valid
        Returns bool result and text error
        """
        pattern, flags = self._searchPatternTextAndFlags()
        try:
            re.compile(pattern, flags)
        except re.error, ex:
            return False, unicode(ex)
        
        return True, None

    def _makeSearchContext(self):
        """Fill search context with actual data
        """

        searchContext = SearchContext(  self._getRegExp(), \
                                        replaceText = self.cbReplace.currentText(), \
                                        searchPath = self.cbPath.currentText(), \
                                        mode = self._mode)

        # TODO search in project
        #self.searchContext.project = core.fileManager().currentProject()
        
        # update masks
        searchContext.mask = \
            [s.strip() for s in self.cbMask.currentText().split(' ')]
        # remove empty
        searchContext.mask = [m for m in searchContext.mask if m]
        
        # TODO update project
        #self.searchContext.project = self.searchContext.project.topLevelProject()

        # update opened files
        for document in core.workspace().openedDocuments():
            searchContext.openedFiles[document.filePath()] = document.text()
        
        # TODO support project
        # update sources files
        #self.searchContext.sourcesFiles = []
        #if self.searchContext.project:
        #    self.searchContext.sourcesFiles = \
        #                self.searchContext.project.topLevelProjectSourceFiles()
        
        return searchContext

    def showMessage (self, status):
        """Show message on the status bar"""
        if not status:
            core.mainWindow().statusBar().clearMessage()
        else:
            core.mainWindow().statusBar().showMessage( status, 30000 )

    def setState(self, state ):
        """Change line edit color according to search result
        """
        widget = self.cbSearch.lineEdit()
        
        color = {SearchWidget.Normal: self._defaultBackgroundColor, \
                 SearchWidget.Good: Qt.green, \
                 SearchWidget.Bad: Qt.red,
                 SearchWidget.Incorrect: Qt.darkYellow}
        
        pal = widget.palette()
        pal.setColor( widget.backgroundRole(), color[state] )
        widget.setPalette( pal )
    
    def searchFile(self, forward, incremental = False):
        """Do search in file operation. Will select next found item
        """
        document = core.workspace().currentDocument()
        regExp = self._getRegExp()

        # get cursor position        
        start, end = document.absSelection()

        if start is None:
            start = 0
            end = 0
        
        if forward:
            if  incremental :
                point = start
            else:
                point = end

            match = regExp.search(document.text(), point)
            if match is None:  # wrap
                match = regExp.search(document.text(), 0)
        else:  # reverse search
            prevMatch = None
            for match in regExp.finditer(document.text()):
                if match.start() >= start:
                    break
                prevMatch = match
            match = prevMatch
            if match is None:  # wrap
                matches = [match for match in regExp.finditer(document.text())]
                if matches:
                    match = matches[-1]
        
        if match is not None:
            document.goTo(absPos = match.start(), selectionLength = len(match.group(0)))
            self.setState(SearchWidget.Good)  # change background acording to result
        else:
            self.setState(SearchWidget.Bad)
        
        # return found state
        return match is not None

    def replaceFile(self):
        """Do one replacement in the file
        """
        document = core.workspace().currentDocument()
        regExp = self._getRegExp()

        start, end = document.absSelection()  # pylint: disable=W0612
        if start is None:
            start = 0
        
        match = regExp.search(document.text(), start)
        
        if match is None:
            match = regExp.search(document.text(), 0)
        
        if match is not None:
            document.goTo(absPos = match.start(), selectionLength = len(match.group(0)))
            replaceText = self.cbReplace.currentText()
            try:
                replaceText = regExp.sub(replaceText, match.group(0))
            except re.error, ex:
                message = unicode(ex.message, 'utf_8')
                message += r'. Probably <i>\group_index</i> used in replacement string, but such group not found. '\
                           r'Try to escape it: <i>\\group_index</i>'
                QMessageBox.critical(None, "Invalid replace string", message)
                # TODO link to replace help
                return
            document.replaceSelectedText(replaceText)
            document.goTo(absPos = match.start() + len(replaceText))
            self.pbNext.click() # move selection to next item
        else:
            self.setState(SearchWidget.Bad)

    def replaceFileAll(self):
        """Do all replacements in the file
        """
        document = core.workspace().currentDocument()
        regExp = self._getRegExp()
        replaceText = self.cbReplace.currentText()

        oldPos = document.absCursorPosition()
        
        document.beginUndoAction()
        
        pos = 0
        count = 0
        match = regExp.search(document.text(), pos)
        while match is not None:
            document.goTo(absPos = match.start(), selectionLength = len(match.group(0)))
            replText = regExp.sub(replaceText, match.group(0))
            document.replaceSelectedText(replText)
            
            count += 1
            
            pos = match.start() + len(replText)
            
            if not match.group(0) and not replText:  # avoid freeze when replacing empty with empty
                pos += 1
            if pos < len(document.text()):
                match = regExp.search(document.text(), pos)
            else:
                match = None

        document.endUndoAction()
        
        if oldPos is not None:
            document.setCursorPosition(absPos = oldPos) # restore cursor position
        self.showMessage( self.tr( "%d occurrence(s) replaced." % count ))

    def searchThread_stateChanged(self):
        """Search thread started or stopped
        """
        self.pbSearchStop.setVisible( self.searchThread.isRunning() )
        self.pbSearch.setVisible( not self.searchThread.isRunning() )
        self.updateWidgets()
        self._progress.setVisible( self.searchThread.isRunning() )

    def searchThread_progressChanged(self, value, total ):
        """Signal from the thread, progress changed
        """
        self._progress.setValue( value )
        self._progress.setMaximum( total )

    def replaceThread_stateChanged(self):
        """Replace thread started or stopped
        """
        self.pbReplaceCheckedStop.setVisible( self._replaceThread.isRunning() )
        self.pbReplaceChecked.setVisible( not self._replaceThread.isRunning() )
        self.updateWidgets()

    def replaceThread_openedFileHandled(self, fileName, content):
        """Replace thread processed currently opened file,
        need update text in the editor
        """
        document = core.workspace().openFile(fileName)
        document.replace(content, startAbsPos=0, endAbsPos=len(document.text()))

    def replaceThread_error(self, error ):
        """Error message from the replace thread
        """
        core.messageToolBar().appendMessage( error )
    
    def _updateActionsState(self):
        """Update actions state according to search context valid state
        """
        valid, error = self._isSearchRegExpValid()
        searchAvailable = valid 
        searchInFileAvailable = valid and core.workspace().currentDocument() is not None
        
        for button in (self.pbNext, self.pbPrevious, self.pbReplace, self.pbReplaceAll):
            button.setEnabled(searchInFileAvailable)
        core.actionManager().action("mNavigation/mSearchReplace/aSearchNext").setEnabled(searchInFileAvailable)
        core.actionManager().action("mNavigation/mSearchReplace/aSearchPrevious").setEnabled(searchInFileAvailable)

        self.pbSearch.setEnabled(searchAvailable)
    
    def _onSearchRegExpChanged(self):
        """User edited search text or checked/unchecked checkboxes
        """
        valid, error = self._isSearchRegExpValid()
        if valid:
            self.setState(self.Normal)
        else:
            core.mainWindow().statusBar().showMessage(error, 5000)
            self.setState(self.Incorrect)
            return
        
        # clear search results if needed.
        if self._mode in (ModeSearch, ModeReplace) and \
           core.workspace().currentDocument() is not None:
            self.searchFile( True, True )

    def cdUp_pressed(self):
        """User pressed "Up" button, need to remove one level from search path
        """
        text = self.cbPath.currentText()
        if not os.path.exists(text):
            return
        self.cbPath.setEditText( os.path.abspath(text + '/' + os.path.pardir))

    def on_pbPrevious_pressed(self):
        """Handler of click on "Previous" button
        """
        self.updateComboBoxes()
        self.searchFile( False )

    def on_pbNext_pressed(self):
        """Handler of click on "Next" button
        """
        self.updateComboBoxes()
        self.searchFile( True, False )

    def on_pbSearch_pressed(self):
        """Handler of click on "Search" button (for search in directory)
        """
        self.setState(SearchWidget.Normal )
        self.updateComboBoxes()
        
        # TODO support project
        #if  self.searchContext._mode & ModeFlagProjectFiles and not self.searchContext.project :
        #    core.messageToolBar().appendMessage( \
        #                        self.tr( "You can't search in project files because there is no opened projet." ) )
        #    return

        self.searchThread.search( self._makeSearchContext() )

    def on_pbSearchStop_pressed(self):
        """Handler of click on "Stop" button. Stop search thread
        """
        self.searchThread.stop()

    def on_pbReplace_pressed(self):
        """Handler of click on "Replace" (in file) button
        """
        self.updateComboBoxes()
        self.replaceFile()

    def on_pbReplaceAll_pressed(self):
        """Handler of click on "Replace all" (in file) button
        """
        self.updateComboBoxes()
        self.replaceFileAll()

    def on_pbReplaceChecked_pressed(self):
        """Handler of click on "Replace checked" (in directory) button
        """
        self.updateComboBoxes()
        self._replaceThread.replace( self._makeSearchContext(), self._dock.getCheckedItems() )

    def on_pbReplaceCheckedStop_pressed(self):
        """Handler of click on "Stop" button when replacing in directory
        """
        self._replaceThread.stop()

    def on_pbBrowse_pressed(self):
        """Handler of click on "Browse" button. Explores FS for search directory path
        """
        path = QFileDialog.getExistingDirectory( self, self.tr( "Search path" ), self.cbPath.currentText() )

        if path:
            self.cbPath.setEditText( path )
