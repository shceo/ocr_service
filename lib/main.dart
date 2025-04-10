import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'ocr_service.dart';
import 'excel_service.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: LoginScreen(),
    );
  }
}

/// Экран входа с центровкой элементов
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  _LoginScreenState createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _passwordController = TextEditingController();
  String? _error;

  void _login() {
    if (_passwordController.text == '1234') {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => const HomeScreen()),
      );
    } else {
      setState(() {
        _error = 'Неверный пароль';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Вход'),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              TextField(
                controller: _passwordController,
                obscureText: true,
                maxLength: 4,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Введите 4-значный пароль',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_error != null)
                Text(
                  _error!,
                  style: const TextStyle(color: Colors.red),
                ),
              const SizedBox(height: 20),
              SizedBox(
                width: buttonWidth,
                height: 50,
                child: ElevatedButton(
                  onPressed: _login,
                  child: const Text('Войти'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Главный экран с плавающей нижней навигационной панелью
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;
  final List<Widget> _pages = [
    const PassportReaderScreen(),
    const SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_currentIndex],
      // Плавающая навигационная панель с отступом от низа
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: Container(
        margin: const EdgeInsets.only(bottom: 20, left: 16, right: 16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
          boxShadow: const [
            BoxShadow(color: Colors.black26, blurRadius: 8),
          ],
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) {
            setState(() {
              _currentIndex = index;
            });
          },
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.home),
              label: 'Главная',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.settings),
              label: 'Настройки',
            ),
          ],
          backgroundColor: Colors.transparent,
          elevation: 0,
          selectedItemColor: Colors.blue,
          unselectedItemColor: Colors.grey,
          type: BottomNavigationBarType.fixed,
        ),
      ),
    );
  }
}

/// Страница чтения паспорта с загрузкой файла, экспортом в Excel и открытием папки
class PassportReaderScreen extends StatefulWidget {
  const PassportReaderScreen({super.key});
  @override
  _PassportReaderScreenState createState() => _PassportReaderScreenState();
}

class _PassportReaderScreenState extends State<PassportReaderScreen> {
  File? _image;
  String? _extractedData;
  String? _error;
  String? _excelFilePath;
  bool _isProcessing = false;
  final ocrService = OCRService();
  List<List<String>> _tableData = [];

  Future<void> _pickImage() async {
    final image = await ImagePicker().pickImage(source: ImageSource.gallery);
    if (image == null) return;
    setState(() {
      _image = File(image.path);
      _isProcessing = true;
      _error = null;
    });
    try {
      final data = await OCRService.extractPassportData(_image!);
      setState(() {
        _extractedData = data;
        _isProcessing = false;
        _tableData = _processExtractedData(data);
      });
    } catch (e) {
      setState(() {
        _error = 'Ошибка при распознавании: $e';
        _isProcessing = false;
      });
    }
  }

  List<List<String>> _processExtractedData(dynamic data) {
    List<List<String>> table = [];
    List<String> rows = data.split('\n');
    for (var row in rows) {
      table.add(row.split(','));
    }
    return table;
  }

  Future<void> _exportToExcel() async {
    if (_tableData.isEmpty) return;
    final fileName = await _getFileNameFromUser();
    if (fileName == null || fileName.isEmpty) return;
    try {
      String filePath = await ExcelService().exportToExcel(_tableData, fileName);
      setState(() {
        _error = 'Данные успешно экспортированы в Excel';
        _excelFilePath = filePath;
      });
    } catch (e) {
      setState(() {
        _error = 'Ошибка при экспорте: $e';
      });
    }
  }

  Future<String?> _getFileNameFromUser() async {
    final controller = TextEditingController(text: 'passport_data_final.xlsx');
    return showDialog<String>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Введите название файла'),
          content: TextField(
            controller: controller,
            decoration: const InputDecoration(
              hintText: 'Имя файла с расширением .xlsx',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(null),
              child: const Text('Отмена'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(controller.text),
              child: const Text('ОК'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _openFolder() async {
    if (_excelFilePath != null) {
      final directory = Directory(_excelFilePath!).parent.path;
      if (Platform.isWindows) {
        await Process.run('explorer', [directory]);
      } else if (Platform.isMacOS) {
        await Process.run('open', [directory]);
      } else if (Platform.isLinux) {
        await Process.run('xdg-open', [directory]);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Чтение паспорта РФ'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Center(
            child: Column(
              children: [
                if (_image != null)
                  Image.file(
                    _image!,
                    height: 200,
                  ),
                const SizedBox(height: 20),
                SizedBox(
                  width: buttonWidth,
                  height: 50,
                  child: ElevatedButton(
                    onPressed: _isProcessing ? null : _pickImage,
                    child: const Text('Загрузить файл'),
                  ),
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: buttonWidth,
                  height: 50,
                  child: ElevatedButton(
                    onPressed: _tableData.isNotEmpty ? _exportToExcel : null,
                    child: const Text('Выгрузить в Excel'),
                  ),
                ),
                if (_excelFilePath != null) ...[
                  const SizedBox(height: 20),
                  Text(
                    'Excel файл сохранён по пути: $_excelFilePath',
                    style: const TextStyle(color: Colors.blue),
                  ),
                  const SizedBox(height: 20),
                  SizedBox(
                    width: buttonWidth,
                    height: 50,
                    child: ElevatedButton(
                      onPressed: _openFolder,
                      child: const Text('Открыть папку'),
                    ),
                  ),
                ],
                const SizedBox(height: 20),
                if (_error != null)
                  Text(
                    _error!,
                    style: const TextStyle(color: Colors.red),
                  ),
                if (_tableData.isNotEmpty) _buildTable(),
                if (_isProcessing) const CircularProgressIndicator(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTable() {
    if (_tableData.isEmpty || _tableData[0].isEmpty) {
      return const Text('Нет данных для отображения.');
    }
    int columnCount = _tableData[0].length;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: List.generate(
          columnCount,
          (index) => DataColumn(
            label: Text(_tableData[0][index].isNotEmpty ? _tableData[0][index] : 'Column ${index + 1}'),
          ),
        ),
        rows: _tableData.skip(1).map((row) {
          List<String> paddedRow = List<String>.from(row);
          if (paddedRow.length < columnCount) {
            paddedRow.addAll(List.filled(columnCount - paddedRow.length, ''));
          } else if (paddedRow.length > columnCount) {
            paddedRow = paddedRow.sublist(0, columnCount);
          }
          return DataRow(
            cells: paddedRow.map((cell) => DataCell(Text(cell))).toList(),
          );
        }).toList(),
      ),
    );
  }
}

/// Страница настроек с современной кнопкой для перехода к смене пароля
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Настройки'),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (context) => const ChangePasswordScreen()),
                  );
                },
                child: const Text('Изменить пароль'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Экран для смены пароля
class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});
  @override
  _ChangePasswordScreenState createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _newPasswordController = TextEditingController();
  String? _message;

  void _changePassword() {
    if (_newPasswordController.text.isEmpty) {
      setState(() {
        _message = 'Пароль не может быть пустым.';
      });
    } else {
      // Здесь можно добавить логику сохранения нового пароля (например, через SharedPreferences)
      setState(() {
        _message = 'Пароль успешно изменён!';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Изменить пароль'),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              TextField(
                controller: _newPasswordController,
                obscureText: true,
                maxLength: 4,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Новый 4-значный пароль',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: buttonWidth,
                height: 50,
                child: ElevatedButton(
                  onPressed: _changePassword,
                  child: const Text('Сохранить'),
                ),
              ),
              const SizedBox(height: 20),
              if (_message != null)
                Text(
                  _message!,
                  style: const TextStyle(color: Colors.green),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
