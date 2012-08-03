#!/bin/sh

QRC_FILE=enkiicons.qrc
RESOURCE_FILE=../enkilib/resources/icons.py

echo '<RCC>' > $QRC_FILE
echo '	<qresource prefix="/enkiicons" >' >> $QRC_FILE
for file in `ls *.png languages/*.png fresh/*.png`; do \
	echo '		<file>'$file'</file>' >> $QRC_FILE;
done
echo '	</qresource>' >>$QRC_FILE
echo '</RCC>' >>$QRC_FILE

pyrcc4 -o $RESOURCE_FILE $QRC_FILE