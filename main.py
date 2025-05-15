from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import chess
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = '7376599895:AAFf7HhcSulogM9UHNPoPgsK8wKt3T-q1So'


class ChessGame:
    def __init__(self, player1_id: int, player2_id: Optional[int] = None):
        self.board = chess.Board()
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.current_player = chess.WHITE
        self.selected_square = None

    def make_move(self, move_str: str) -> bool:
        try:
            move = self.board.parse_uci(move_str)
            if move in self.board.legal_moves:
                self.board.push(move)
                self.current_player = not self.current_player
                self.selected_square = None
                return True
            return False
        except ValueError:
            return False

    def get_board_buttons(self) -> InlineKeyboardMarkup:
        buttons = []
        for row in range(7, -1, -1):
            row_buttons = []
            for col in range(8):
                square = chess.square(col, row)
                piece = self.board.piece_at(square)
                symbol = self.get_piece_symbol(piece) if piece else " "

                if self.selected_square == square:
                    prefix = ">"
                    suffix = "<"
                else:
                    prefix = suffix = ""

                button_text = f"{prefix}{symbol}{suffix}"
                button_data = f"square_{chess.square_name(square)}"
                row_buttons.append(InlineKeyboardButton(button_text, callback_data=button_data))
            buttons.append(row_buttons)

        buttons.append([
            InlineKeyboardButton("Отменить выбор", callback_data="cancel_select"),
            InlineKeyboardButton("Сдаться", callback_data="resign")
        ])

        return InlineKeyboardMarkup(buttons)

    def get_piece_symbol(self, piece: chess.Piece) -> str:
        symbols = {
            'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
            'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
        }
        return symbols.get(piece.symbol(), piece.symbol())

    def get_current_player_color(self) -> str:
        return "Белые" if self.current_player == chess.WHITE else "Черные"


class ChessBot:
    def __init__(self):
        self.games: Dict[int, ChessGame] = {}
        self.waiting_players: Dict[int, int] = {}
        self.load_saved_games()

    def save_game(self, chat_id: int) -> bool:
        if chat_id not in self.games:
            return False

        game = self.games[chat_id]
        filename = f"game_{chat_id}.txt"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Player 1 ID: {game.player1_id}\n")
                f.write(f"Player 2 ID: {game.player2_id}\n")
                f.write(f"Current Player: {'WHITE' if game.current_player == chess.WHITE else 'BLACK'}\n")
                f.write("\nMove History:\n")
                f.write(" ".join(str(move) for move in game.board.move_stack))
            return True
        except IOError:
            logging.error(f"Ошибка при сохранении игры в файл {filename}")
            return False

    def load_game(self, chat_id: int) -> Optional[ChessGame]:
        filename = f"game_{chat_id}.txt"
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                player1_id = int(lines[0].split(':')[1].strip())
                player2_id = int(lines[1].split(':')[1].strip()) if lines[1].split(':')[1].strip() else None
                game = ChessGame(player1_id, player2_id)
                current_player_str = lines[2].split(':')[1].strip()
                game.current_player = chess.WHITE if current_player_str == 'WHITE' else chess.BLACK
                move_history = lines[-1].strip().split()
                for move_str in move_history:
                    move = chess.Move.from_uci(move_str)
                    if move in game.board.legal_moves:
                        game.board.push(move)
                return game
        except (IOError, IndexError, ValueError):
            logging.error(f"Ошибка при загрузке игры из файла {filename}")
            return None

    def load_saved_games(self):
        import os
        for filename in os.listdir():
            if filename.startswith('game_') and filename.endswith('.txt'):
                chat_id = int(filename.split('_')[1].split('.')[0])
                game = self.load_game(chat_id)
                if game:
                    self.games[chat_id] = game
                    logging.info(f"Загружена сохраненная игра для чата {chat_id}")

    async def start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        player_id = update.effective_user.id

        # Удаляем старую игру, если она есть
        if chat_id in self.games:
            del self.games[chat_id]
            try:
                import os
                filename = f"game_{chat_id}.txt"
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception as e:
                logging.error(f"Ошибка при удалении файла игры: {e}")

        # Удаляем из ожидающих игроков, если есть
        if player_id in self.waiting_players:
            del self.waiting_players[player_id]

        # Создаем новую игру
        self.waiting_players[player_id] = chat_id
        game = ChessGame(player_id)
        self.games[chat_id] = game

        keyboard = [
            [InlineKeyboardButton("Принять вызов", callback_data=f"accept_{chat_id}")]
        ]

        await update.message.reply_text(
            "Начинаем новую игру!\n"
            "Ищу соперника...\n"
            "Поделитесь этой ссылкой с другом:\n"
            f"https://t.me/{context.bot.username}?start={chat_id}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def accept_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        chat_id = int(query.data.split('_')[1])
        player_id = query.from_user.id

        if chat_id not in self.games:
            await query.edit_message_text("Игра не найдена!")
            return

        game = self.games[chat_id]
        if game.player2_id is not None:
            await query.edit_message_text("Игра уже началась!")
            return

        game.player2_id = player_id

        await query.edit_message_text(
            f"{game.get_current_player_color()} ходят\n"
            "Выберите фигуру для хода:",
            reply_markup=game.get_board_buttons()
        )

    async def handle_square_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        chat_id = query.message.chat_id
        player_id = query.from_user.id

        if chat_id not in self.games:
            await query.edit_message_text("Игра не найдена!")
            return

        game = self.games[chat_id]

        if player_id not in [game.player1_id, game.player2_id]:
            await query.edit_message_text("Вы не участник этой игры!")
            return

        current_player_id = game.player1_id if game.current_player == chess.WHITE else game.player2_id
        if player_id != current_player_id:
            await query.answer("Сейчас не ваш ход!")
            return

        if query.data.startswith("square_"):
            square_name = query.data.split('_')[1]
            square = chess.parse_square(square_name)

            if game.selected_square is None:
                piece = game.board.piece_at(square)
                if piece and piece.color == game.current_player:
                    game.selected_square = square
                    await query.edit_message_text(
                        f"{game.get_current_player_color()} ходят\n"
                        f"Выбрана фигура на {square_name}. Выберите клетку для хода:",
                        reply_markup=game.get_board_buttons()
                    )
                else:
                    await query.answer("Выберите свою фигуру!")
            else:
                move = chess.Move(game.selected_square, square)

                if move in game.board.legal_moves:
                    game.make_move(move.uci())
                    self.save_game(chat_id)

                    if game.board.is_game_over():
                        result = "Игра окончена! "
                        if game.board.is_checkmate():
                            result += "Мат!"
                        elif game.board.is_stalemate():
                            result += "Пат!"
                        elif game.board.is_insufficient_material():
                            result += "Недостаточно материала!"
                        else:
                            result += "Ничья!"

                        await query.edit_message_text(
                            f"{result}\n"
                            f"Последняя позиция:",
                            reply_markup=game.get_board_buttons()
                        )
                        del self.games[chat_id]
                    else:
                        await query.edit_message_text(
                            f"{game.get_current_player_color()} ходят\n"
                            "Выберите фигуру для хода:",
                            reply_markup=game.get_board_buttons()
                        )
                else:
                    await query.answer("Недопустимый ход!")
                    game.selected_square = None
                    await query.edit_message_text(
                        f"{game.get_current_player_color()} ходят\n"
                        "Недопустимый ход. Выберите фигуру снова:",
                        reply_markup=game.get_board_buttons()
                    )

        elif query.data == "cancel_select":
            game.selected_square = None
            await query.edit_message_text(
                f"{game.get_current_player_color()} ходят\n"
                "Выбор отменен. Выберите фигуру для хода:",
                reply_markup=game.get_board_buttons()
            )

        elif query.data == "resign":
            resign_color = "Белые" if game.current_player == chess.WHITE else "Черные"
            winner_color = "Черные" if game.current_player == chess.WHITE else "Белые"

            await query.edit_message_text(
                f"{resign_color} сдаются!\n"
                f"Победили {winner_color}!",
                reply_markup=game.get_board_buttons()
            )
            del self.games[chat_id]

    async def end_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if chat_id in self.games:
            del self.games[chat_id]
            try:
                import os
                filename = f"game_{chat_id}.txt"
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception as e:
                logging.error(f"Ошибка при удалении файла игры: {e}")
            await update.message.reply_text("Игра завершена!")
        else:
            await update.message.reply_text("Нет активной игры для завершения!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать в шахматный бот!\n"
        "/play - начать новую игру\n"
        "/end_game - закончить текущую игру\n"
        "/help - показать это сообщение"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать в шахматный бот!\n"
        "/play - начать новую игру\n"
        "/end_game - закончить текущую игру\n"
        "/help - показать это сообщение"
    )


def main():
    token = BOT_TOKEN
    bot = ChessBot()

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", bot.start_game))
    application.add_handler(CommandHandler("end_game", bot.end_game))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CallbackQueryHandler(bot.accept_game, pattern=r"^accept_\d+$"))
    application.add_handler(CallbackQueryHandler(bot.handle_square_selection))

    application.run_polling()


if __name__ == '__main__':
    main()