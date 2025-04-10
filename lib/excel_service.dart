import 'package:excel/excel.dart';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

class ExcelService {
  Future<String> exportToExcel(List<List<String>> tableData, String fileName) async {
    try {
      // Логируем входные данные
      print("Полученные данные для экспорта: $tableData");
      if (tableData.isEmpty) {
        throw Exception('Ошибка: tableData пуст. Нет данных для записи.');
      }

      var excel = Excel.createExcel();
      Sheet sheetObject = excel['Sheet1'];

      // Заголовки столбцов
      List<String> headers = [
        'Фамилия',           // Last Name
        'Имя',               // First Name
        'Отчество',          // Patronymic
        'Пол',               // Gender
        'Дата выдачи',       // Issue Date
        'Место выдачи',      // Place of Issue
        'Серия',             // Serial Number
        'Дата рождения',     // Date of Birth
        'Место рождения',    // Place of Birth
        'Код подразделения', // Division Code
      ];

      // Записываем заголовки
      sheetObject.appendRow(headers.map((header) => TextCellValue(header)).toList());

      // Аккумулируем все сформированные строки данных
      List<List<String>> completeRows = [];

      // Обрабатываем каждую строку данных
      for (List<String> row in tableData) {
        // Создаем пустой массив с количеством ячеек, равным числу заголовков
        List<String> completeRow = List<String>.filled(headers.length, '');
        bool hasData = false;

        for (String cell in row) {
          String field = _classifyField(cell);
          print("Классификация: '$cell' -> '$field'");

          // Пропускаем строки, которые не несут полезной информации
          if (field == 'ignore') continue;

          // Если в ячейке содержится полное ФИО (три слова), разделяем его
          if (field == 'ФИО') {
            List<String> nameParts = cell.split(' ').where((s) => s.isNotEmpty).toList();
            if (nameParts.length >= 3) {
              if (completeRow[0].isEmpty) { completeRow[0] = nameParts[0]; }
              if (completeRow[1].isEmpty) { completeRow[1] = nameParts[1]; }
              if (completeRow[2].isEmpty) { completeRow[2] = nameParts[2]; }
              hasData = true;
            }
            continue;
          }

          // Присваиваем значение в соответствующий столбец, если он еще не заполнен
          switch (field) {
            case 'Фамилия':
              if (completeRow[0].isEmpty) {
                completeRow[0] = cell;
                hasData = true;
              }
              break;
            case 'Имя':
              if (completeRow[1].isEmpty) {
                completeRow[1] = cell;
                hasData = true;
              }
              break;
            case 'Отчество':
              if (completeRow[2].isEmpty) {
                completeRow[2] = cell;
                hasData = true;
              }
              break;
            case 'Пол':
              if (completeRow[3].isEmpty) {
                completeRow[3] = cell;
                hasData = true;
              }
              break;
            case 'Дата выдачи':
              if (completeRow[4].isEmpty) {
                completeRow[4] = cell;
                hasData = true;
              }
              break;
            case 'Место выдачи':
              if (completeRow[5].isEmpty) {
                completeRow[5] = cell;
                hasData = true;
              }
              break;
            case 'Серия':
              if (completeRow[6].isEmpty) {
                completeRow[6] = cell;
                hasData = true;
              }
              break;
            case 'Дата рождения':
              if (completeRow[7].isEmpty) {
                completeRow[7] = cell;
                hasData = true;
              }
              break;
            case 'Место рождения':
              if (completeRow[8].isEmpty) {
                completeRow[8] = cell;
                hasData = true;
              }
              break;
            case 'Код подразделения':
              if (completeRow[9].isEmpty) {
                completeRow[9] = cell;
                hasData = true;
              }
              break;
          }
        }

        // Если строка содержит хотя бы одно значение, добавляем её в аккумулятор
        if (hasData) {
          completeRows.add(completeRow);
        }
      }

      // Если есть собранные данные, объединяем значения каждого столбца в одну строку
      if (completeRows.isNotEmpty) {
        List<String> concatenatedRow = List<String>.filled(headers.length, '');
        for (int col = 0; col < headers.length; col++) {
          // Собираем все данные для данного столбца в порядке, в котором они пришли
          List<String> colData = [];
          for (var row in completeRows) {
            if (row[col].isNotEmpty) {
              colData.add(row[col]);
            }
          }
          // Объединяем данные с разделителем (например, перевод строки)
          concatenatedRow[col] = colData.join('\n');
        }
        // Добавляем итоговую строку под заголовками
        sheetObject.appendRow(concatenatedRow.map((cell) => TextCellValue(cell)).toList());
      }

      // Кодируем и сохраняем Excel-файл с именем, выбранным пользователем
      final fileBytes = excel.encode();
      if (fileBytes == null) {
        throw Exception("Ошибка: Excel-файл не закодировался!");
      }
      final directory = await getApplicationDocumentsDirectory();
      String filePath = path.join(directory.path, fileName);
      File(filePath)
        ..createSync(recursive: true)
        ..writeAsBytesSync(fileBytes);
      print("Файл сохранен по пути: $filePath");

      return filePath;
    } catch (e) {
      throw Exception('Ошибка при экспорте в Excel: $e');
    }
  }

  /// Улучшенная логика классификации поля
  String _classifyField(String cell) {
    String cleanedCell = cell.toLowerCase().trim();

    // Игнорируем строки, содержащие заголовки, MRZ или служебные символы
    if (cleanedCell.contains('паспорт') ||
        cleanedCell.contains('pnrus') ||
        cleanedCell.contains('<<')) {
      return 'ignore';
    }

    // Если значение соответствует формату даты (dd.mm.yyyy)
    RegExp dateRegex = RegExp(r'\b\d{2}\.\d{2}\.\d{4}\b');
    if (dateRegex.hasMatch(cleanedCell)) {
      // Если в строке есть слова, указывающие на выдачу, назначаем Дата выдачи,
      // иначе считаем, что это дата рождения
      if (cleanedCell.contains('выдан')) {
         return 'Дата выдачи';
      } else {
         return 'Дата рождения';
      }
    }

    // Определяем пол
    if (cleanedCell == 'муж' || cleanedCell == 'муж.' || 
        cleanedCell == 'жен' || cleanedCell == 'жен.') {
      return 'Пол';
    }

    // Проверка серии паспорта: формат 000-000 или ровно 4 цифры
    RegExp seriesRegex = RegExp(r'^\d{3}-\d{3}$');
    if (seriesRegex.hasMatch(cleanedCell)) {
      return 'Серия';
    }
    if (cleanedCell.length == 4 && int.tryParse(cleanedCell) != null) {
      return 'Серия';
    }

    // Проверка кода подразделения: 6 цифр
    if (cleanedCell.length == 6 && int.tryParse(cleanedCell) != null) {
      return 'Код подразделения';
    }

    // Если строка содержит ключевые слова, указывающие на орган выдачи паспорта,
    // назначаем ее как Место выдачи
    if (cleanedCell.contains('гу ') ||
        cleanedCell.contains('мвд') ||
        cleanedCell.contains('по ') ||
        cleanedCell.contains('российская федерация')) {
      return 'Место выдачи';
    }

    // Если строка содержит типичные указания на место (город, область, район)
    if (cleanedCell.contains('г.') ||
        cleanedCell.contains('обл.') ||
        cleanedCell.contains('район')) {
      return 'Место рождения';
    }

    // Если в ячейке содержится три слова, предполагаем, что это полное ФИО
    List<String> words = cleanedCell.split(' ').where((s) => s.isNotEmpty).toList();
    if (words.length == 3) {
      return 'ФИО';
    }

    // Если слово заканчивается на типичные окончания для отчеств
    if (cleanedCell.endsWith('вич') || cleanedCell.endsWith('вна')) {
      return 'Отчество';
    }

    // Если ячейка состоит из одного слова, состоящего только из букв, считаем, что это имя
    if (words.length == 1 && RegExp(r'^[а-яё]+$', caseSensitive: false).hasMatch(cleanedCell)) {
      return 'Имя';
    }

    return 'Неопределено';
  }
}
